#!/usr/bin/env python3
"""
Synthetic MIMIC-IV-shaped blood transfusion data, with a sealed answer key.

Writes a small subset of the MIMIC-IV schema (hosp/patients, hosp/admissions,
icu/icustays, icu/d_items, icu/inputevents) as gzipped CSVs, so SQL written
against it should run on real MIMIC-IV with only item-ID changes.

Demand mostly follows Elston & Pickerel (Poisson arrivals x logarithmic
transfusion sizes) but departs from it on purpose: patient frailty, repeat
episodes, weekday/night effects, drift across periods, and a heavy tail.
The true parameters are drawn at random and written ONLY to the answer key.

Data traps planted in inputevents (all recorded in the answer key):
  - bags split across two rows (linked by linkorderid)
  - 'Rewritten' rows with wrong amounts next to the corrected row
  - partially infused 'Stopped' bags
  - exact duplicate rows (ETL glitch)
  - a legacy platelet item logged in donor units, not mL (2008-2010 only)
  - platelets spread over several item IDs, plus look-alike decoy items
  - late storetime values
  - per-patient date shifting that preserves day of week

Usage:
    uv run python generate_synthetic_mimic.py --out synth --patients 50000
    uv run python generate_synthetic_mimic.py --out synth --seed 42   # reproducible

Do NOT open synth/answer_key/ until you have finished the phase you're grading.
"""
import argparse
import json
import os
from collections import Counter
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

REAL_START = datetime(2008, 1, 1)
REAL_END = datetime(2019, 12, 31, 23, 59)
GROUPS = [(2008, 2010), (2011, 2013), (2014, 2016), (2017, 2019)]
FMT = "%Y-%m-%d %H:%M:%S"

# Columns and types of each table written, in MIMIC-IV order, following
# mimic-code/mimic-iv/buildmimic/postgres/create.sql (as DuckDB types).
SCHEMA = {
    "hosp/patients": [
        ("subject_id", "INTEGER"), ("gender", "VARCHAR"), ("anchor_age", "SMALLINT"),
        ("anchor_year", "SMALLINT"), ("anchor_year_group", "VARCHAR"), ("dod", "DATE"),
    ],
    "hosp/admissions": [
        ("subject_id", "INTEGER"), ("hadm_id", "INTEGER"), ("admittime", "TIMESTAMP"),
        ("dischtime", "TIMESTAMP"), ("deathtime", "TIMESTAMP"), ("admission_type", "VARCHAR"),
        ("admit_provider_id", "VARCHAR"), ("admission_location", "VARCHAR"),
        ("discharge_location", "VARCHAR"), ("insurance", "VARCHAR"), ("language", "VARCHAR"),
        ("marital_status", "VARCHAR"), ("race", "VARCHAR"), ("edregtime", "TIMESTAMP"),
        ("edouttime", "TIMESTAMP"), ("hospital_expire_flag", "SMALLINT"),
    ],
    "icu/icustays": [
        ("subject_id", "INTEGER"), ("hadm_id", "INTEGER"), ("stay_id", "INTEGER"),
        ("first_careunit", "VARCHAR"), ("last_careunit", "VARCHAR"), ("intime", "TIMESTAMP"),
        ("outtime", "TIMESTAMP"), ("los", "DOUBLE"),
    ],
    "icu/d_items": [
        ("itemid", "INTEGER"), ("label", "VARCHAR"), ("abbreviation", "VARCHAR"),
        ("linksto", "VARCHAR"), ("category", "VARCHAR"), ("unitname", "VARCHAR"),
        ("param_type", "VARCHAR"), ("lownormalvalue", "DOUBLE"), ("highnormalvalue", "DOUBLE"),
    ],
    "icu/inputevents": [
        ("subject_id", "INTEGER"), ("hadm_id", "INTEGER"), ("stay_id", "INTEGER"),
        ("caregiver_id", "INTEGER"), ("starttime", "TIMESTAMP"), ("endtime", "TIMESTAMP"),
        ("storetime", "TIMESTAMP"), ("itemid", "INTEGER"), ("amount", "DOUBLE"),
        ("amountuom", "VARCHAR"), ("rate", "DOUBLE"), ("rateuom", "VARCHAR"),
        ("orderid", "INTEGER"), ("linkorderid", "INTEGER"), ("ordercategoryname", "VARCHAR"),
        ("secondaryordercategoryname", "VARCHAR"), ("ordercomponenttypedescription", "VARCHAR"),
        ("ordercategorydescription", "VARCHAR"), ("patientweight", "DOUBLE"),
        ("totalamount", "DOUBLE"), ("totalamountuom", "VARCHAR"), ("isopenbag", "SMALLINT"),
        ("continueinnextdept", "SMALLINT"), ("statusdescription", "VARCHAR"),
        ("originalamount", "DOUBLE"), ("originalrate", "DOUBLE"),
    ],
}

# Synthetic item IDs (990xxx) so nobody mistakes them for real MIMIC IDs.
D_ITEMS = [
    # itemid, label, abbreviation, linksto, category, unitname, param_type,
    # lownormalvalue, highnormalvalue
    (990101, "Platelets", "Platelets", "inputevents", "Blood Products/Colloids", "mL", "Solution", None, None),
    (990102, "Platelet Pool", "Plt Pool", "inputevents", "Blood Products/Colloids", "units", "Solution", None, None),
    (990103, "Apheresis Platelets", "Aph Plt", "inputevents", "Blood Products/Colloids", "mL", "Solution", None, None),
    (990111, "Packed Red Blood Cells", "PRBCs", "inputevents", "Blood Products/Colloids", "mL", "Solution", None, None),
    (990121, "Fresh Frozen Plasma", "FFP", "inputevents", "Blood Products/Colloids", "mL", "Solution", None, None),
    (990131, "Cryoprecipitate", "Cryo", "inputevents", "Blood Products/Colloids", "mL", "Solution", None, None),
    (990141, "Albumin 5%", "Albumin 5%", "inputevents", "Blood Products/Colloids", "mL", "Solution", None, None),
    (990161, "NaCl 0.9%", "NS", "inputevents", "Fluids/Intake", "mL", "Solution", None, None),
    (990151, "Platelet Count", "PLT", "chartevents", "Labs", "K/uL", "Numeric", None, None),
    (990152, "Platelet Transfusion Consent", "Plt Consent", "chartevents", "Consent", None, "Checkbox", None, None),
]
# (ordercategoryname, secondaryordercategoryname) by itemid; everything else is blood.
ORDER_CATEGORY = {
    990141: ("04-Fluids (Colloids)", None),
    990161: ("02-Fluids (Crystalloids)", "Additive (Crystalloid)"),
}
BLOOD_ORDER_CATEGORY = ("07-Blood Products", None)

# Value sets and rough frequencies below follow the MIMIC-IV v2.2 demo.
CAREUNITS = [
    "Medical Intensive Care Unit (MICU)", "Surgical Intensive Care Unit (SICU)",
    "Cardiac Vascular Intensive Care Unit (CVICU)", "Trauma SICU (TSICU)",
    "Coronary Care Unit (CCU)",
]
ADMISSION_LOCATION = {  # by admission_type: (values, probabilities)
    "EW EMER.": (["EMERGENCY ROOM", "WALK-IN/SELF REFERRAL"], [0.95, 0.05]),
    "URGENT": (["TRANSFER FROM HOSPITAL", "PHYSICIAN REFERRAL", "EMERGENCY ROOM"], [0.5, 0.3, 0.2]),
    "ELECTIVE": (["PHYSICIAN REFERRAL", "CLINIC REFERRAL"], [0.8, 0.2]),
    "SURGICAL SAME DAY ADMISSION": (["PHYSICIAN REFERRAL", "PROCEDURE SITE"], [0.7, 0.3]),
}
ED_VISIT_PROB = {"EW EMER.": 0.94, "URGENT": 0.21}
DISCHARGE_LOCATION = (  # nobody dies in this simulation, so no DIED
    ["HOME HEALTH CARE", "HOME", "SKILLED NURSING FACILITY", "REHAB",
     "CHRONIC/LONG TERM ACUTE CARE", "HOSPICE", "AGAINST ADVICE", None],
    [0.30, 0.30, 0.15, 0.06, 0.04, 0.02, 0.02, 0.11],
)
INSURANCE = (["Other", "Medicare", "Medicaid"], [0.54, 0.38, 0.08])
LANGUAGE = (["ENGLISH", "?"], [0.93, 0.07])
MARITAL_STATUS = (["SINGLE", "MARRIED", "WIDOWED", "DIVORCED", None], [0.40, 0.26, 0.20, 0.10, 0.04])
RACE = (
    ["WHITE", "BLACK/AFRICAN AMERICAN", "UNKNOWN", "HISPANIC/LATINO - PUERTO RICAN",
     "ASIAN", "OTHER", "UNABLE TO OBTAIN", "PATIENT DECLINED TO ANSWER"],
    [0.62, 0.17, 0.06, 0.05, 0.04, 0.03, 0.02, 0.01],
)
PRODUCT_VOLUME = {  # mean, sd in mL
    "platelets": (250, 25), "rbc": (320, 20), "ffp": (260, 20),
    "cryo": (100, 15), "albumin": (250, 0.1), "saline": (50, 10),
}


def group_label(year):
    for a, b in GROUPS:
        if a <= year <= b:
            return f"{a} - {b}"
    raise ValueError(year)


def draw_params(rng):
    u = lambda a, b: float(rng.uniform(a, b))
    return {
        "los_median_days": u(1.8, 2.6),
        "los_sigma": u(0.7, 0.95),
        "stays_per_patient_extra_mean": u(0.2, 0.4),
        "plt_need_prob": u(0.06, 0.12),
        "frailty_gamma_shape": u(1.5, 4.0),
        "period_multiplier": {group_label(a): u(0.8, 1.2) for a, _ in GROUPS},
        "onset_mean_fraction_of_los": u(0.25, 0.5),
        "weekend_accept_multiplier": u(0.7, 0.95),
        "night_accept_multiplier": u(0.5, 0.8),
        "plt_repeat_prob": u(0.2, 0.4),
        "repeat_gap_hours": [12, 72],
        "within_episode_gap_minutes": [0, 120],
        "plt_logseries_theta": u(0.4, 0.65),
        "plt_tail_prob": u(0.03, 0.08),
        "plt_tail_geometric_p": u(0.2, 0.35),
        "rbc_indep_prob": u(0.15, 0.25),
        "rbc_given_plt_prob": u(0.3, 0.5),
        "rbc_logseries_theta": u(0.45, 0.65),
        "ffp_indep_prob": u(0.05, 0.10),
        "ffp_given_plt_prob": u(0.15, 0.30),
        "ffp_logseries_theta": u(0.4, 0.6),
        "cryo_prob": u(0.01, 0.03),
        "albumin_prob": u(0.08, 0.15),
        "saline_prob": u(0.25, 0.4),
        "trap_split_prob": u(0.08, 0.15),
        "trap_stopped_prob": u(0.02, 0.05),
        "trap_rewritten_prob": u(0.02, 0.05),
        "trap_duplicate_prob": u(0.003, 0.01),
        "trap_late_storetime_prob": u(0.03, 0.08),
        "legacy_pool_share_2008_2010": u(0.5, 0.8),
        "apheresis_share": u(0.2, 0.4),
    }


class Generator:
    def __init__(self, rng, p):
        self.rng, self.p = rng, p
        self.patients, self.admissions, self.stays = [], [], []
        self.rows, self.bags, self.episodes, self.row_key = [], [], [], []
        self.dropped = Counter()  # candidate episodes pushed past ICU discharge
        # Descriptive columns draw from their own stream, so adding or changing
        # them never changes the transfusion data for a given seed.
        self.fill = rng.spawn(1)[0]
        alnum = list("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        self.providers = ["P" + "".join(self.fill.choice(alnum, 5)) for _ in range(2000)]
        self.next_order = 10_000_000
        self.next_bag = 1
        self.next_episode = 1

    # ---------- helpers ----------
    def u(self, a, b):
        return float(self.rng.uniform(a, b))

    def sample_onset(self, real_in, los_h):
        """Hours after ICU admission; thinned for weekends and nights."""
        p = self.p
        for _ in range(50):
            t = self.rng.exponential(los_h * p["onset_mean_fraction_of_los"])
            if t >= los_h:
                continue
            ts = real_in + timedelta(hours=t)
            accept = 1.0
            if ts.weekday() >= 5:
                accept *= p["weekend_accept_multiplier"]
            if ts.hour < 8 or ts.hour >= 20:
                accept *= p["night_accept_multiplier"]
            if self.rng.random() < accept:
                return t
        return None

    def bag_count(self, product):
        p = self.p
        if product == "platelets":
            if self.rng.random() < p["plt_tail_prob"]:
                return 3 + int(self.rng.geometric(p["plt_tail_geometric_p"]))
            return int(self.rng.logseries(p["plt_logseries_theta"]))
        if product in ("rbc", "ffp"):
            return int(self.rng.logseries(p[f"{product}_logseries_theta"]))
        if product == "cryo":
            return int(self.rng.logseries(0.5))
        return 1  # albumin, saline

    # ---------- episodes and bags ----------
    def make_episode(self, stay, product, onset_h, n_bags=None, delayed=False):
        """Emit one episode's bags; return when its last bag ended (hours after intime)."""
        los_h = stay["los_h"]
        n = n_bags or self.bag_count(product)
        ep_id = self.next_episode
        self.next_episode += 1
        t = last_end = onset_h
        made = 0
        for _ in range(n):
            if t >= los_h:
                break  # patient left the ICU; episode truncated
            dur_min = self.u(30, 60) if product != "saline" else self.u(5, 15)
            start = stay["real_in"] + timedelta(hours=t)
            end = self.emit_bag(stay, product, ep_id, start, start + timedelta(minutes=dur_min))
            made += 1
            last_end = (end - stay["real_in"]).total_seconds() / 3600
            t = last_end + self.u(*self.p["within_episode_gap_minutes"]) / 60.0
        if made:
            self.episodes.append({
                "episode_id": ep_id, "subject_id": stay["subject_id"],
                "stay_id": stay["stay_id"], "product": product,
                "real_start": stay["real_in"] + timedelta(hours=onset_h),
                "n_bags": made, "n_intended": n, "truncated": made < n,
                "delayed": delayed,
            })
        return last_end

    def schedule_episodes(self, stay, product, onsets):
        """Emit one product's episodes in time order, at least 12 h apart.

        A candidate starting within 12 h of the previous episode's end is
        pushed back to 12-72 h after it, like a repeat episode, and dropped
        if that falls after ICU discharge.
        """
        min_gap = self.p["repeat_gap_hours"][0]
        prev_end = None
        for t in sorted(onsets):
            delayed = prev_end is not None and t < prev_end + min_gap
            if delayed:
                t = prev_end + self.u(*self.p["repeat_gap_hours"])
            if t >= stay["los_h"]:
                self.dropped[product] += 1
                continue
            prev_end = self.make_episode(stay, product, t, delayed=delayed)

    def emit_bag(self, stay, product, ep_id, start, end):
        """Write one bag's inputevents rows; return when its last row ends."""
        p, rng = self.p, self.rng
        bag_id = self.next_bag
        self.next_bag += 1
        mean, sd = PRODUCT_VOLUME[product]
        vol = round(max(20.0, rng.normal(mean, sd)), 1)
        itemid, uom, amount = {
            "rbc": 990111, "ffp": 990121, "cryo": 990131,
            "albumin": 990141, "saline": 990161,
        }.get(product, None), "ml", vol  # inputevents spells it "ml"; d_items "mL"
        legacy = False
        if product == "platelets":
            if start.year <= 2010 and rng.random() < p["legacy_pool_share_2008_2010"]:
                itemid, uom = 990102, "units"
                amount = float(rng.choice([4, 5, 6], p=[0.2, 0.4, 0.4]))  # donor units
                legacy = True
            elif rng.random() < p["apheresis_share"]:
                itemid = 990103
            else:
                itemid = 990101
        self.bags.append({
            "bag_id": bag_id, "subject_id": stay["subject_id"],
            "hadm_id": stay["hadm_id"], "stay_id": stay["stay_id"],
            "product": product, "episode_id": ep_id, "itemid": itemid,
            "real_start": start, "shifted_start": start + stay["shift"],
            "volume_ml": vol,
        })

        link = self.next_order
        # Bag-level columns: totalamount is the bag size, originalrate the ordered rate.
        bag = {"total": amount, "uom": uom,
               "rate": round(amount / ((end - start).total_seconds() / 3600), 2)
               if uom == "ml" else None}
        segments = []  # (start, end, amount, originalamount = left at start, status, trap)
        r = rng.random()
        if product != "saline" and not legacy and r < p["trap_split_prob"]:
            frac = self.u(0.3, 0.7)
            mid = start + (end - start) * frac
            pause = timedelta(minutes=self.u(0, 20))
            a1 = round(amount * frac, 1)
            rest = round(amount - a1, 1)
            segments.append((start, mid, a1, amount, "Paused", "split"))
            segments.append((mid + pause, end + pause, rest, rest, "FinishedRunning", "split"))
        elif product != "saline" and r < p["trap_split_prob"] + p["trap_stopped_prob"]:
            partial = amount if legacy else round(amount * self.u(0.3, 0.9), 1)
            segments.append((start, end, partial, amount, "Stopped", "stopped"))
        else:
            segments.append((start, end, amount, amount, "FinishedRunning", None))

        for s, e, a, orig, status, trap in segments:
            self.add_row(stay, itemid, s, e, a, orig, bag, status, link, bag_id, trap, valid=True)
            if product != "saline" and rng.random() < p["trap_rewritten_prob"]:
                wrong = round(a * float(rng.choice([10, 0.1, 2])), 1)
                self.add_row(stay, itemid, s, e, wrong, orig, bag, "Rewritten", link, bag_id,
                             "rewritten", valid=False)
        return segments[-1][1]

    def add_row(self, stay, itemid, s, e, amount, original, bag, status, link, bag_id, trap, valid):
        p, rng = self.p, self.rng
        orderid = self.next_order
        self.next_order += 1
        s_sh, e_sh = s + stay["shift"], e + stay["shift"]
        late = rng.random() < p["trap_late_storetime_prob"]
        store = e_sh + timedelta(hours=self.u(2, 10) if late else self.u(0, 0.5))
        hours = max((e - s).total_seconds() / 3600, 1e-6)
        uom = bag["uom"]
        category, secondary = ORDER_CATEGORY.get(itemid, BLOOD_ORDER_CATEGORY)
        row = {
            "subject_id": stay["subject_id"], "hadm_id": stay["hadm_id"],
            "stay_id": stay["stay_id"], "caregiver_id": int(rng.integers(1000, 9999)),
            "starttime": s_sh.strftime(FMT), "endtime": e_sh.strftime(FMT),
            "storetime": store.strftime(FMT), "itemid": itemid,
            "amount": amount, "amountuom": uom,
            "rate": round(amount / hours, 2) if uom == "ml" else None,
            "rateuom": "mL/hour" if uom == "ml" else None,
            "orderid": orderid, "linkorderid": link,
            "ordercategoryname": category, "secondaryordercategoryname": secondary,
            "ordercomponenttypedescription": "Main order parameter",
            "ordercategorydescription": "Continuous IV",
            "patientweight": stay["weight"],
            "totalamount": bag["total"], "totalamountuom": uom,
            "isopenbag": 0, "continueinnextdept": 0, "statusdescription": status,
            "originalamount": original, "originalrate": bag["rate"],
        }
        self.rows.append(row)
        dup = rng.random() < p["trap_duplicate_prob"]
        if dup:
            self.rows.append(dict(row))
        traps = [t for t in [trap, "late_storetime" if late else None,
                             "legacy_units" if uom == "units" else None] if t]
        self.row_key.append({
            "orderid": orderid, "bag_id": bag_id, "is_valid": valid,
            "duplicated": dup, "traps": ";".join(traps),
        })

    # ---------- patients and stays ----------
    def run(self, n_patients):
        p, rng = self.p, self.rng
        span = (REAL_END - REAL_START).total_seconds()
        hadm, stay_id = 20_000_000, 30_000_000
        for i in range(n_patients):
            subject_id = 10_000_000 + i
            first_in = REAL_START + timedelta(seconds=float(rng.uniform(0, span)))
            # Shift by whole weeks so day of week is preserved.
            target_year = int(rng.integers(2110, 2191))
            weeks = round((datetime(target_year, 6, 1) - first_in).days / 7)
            shift = timedelta(days=7 * weeks)
            frailty = float(rng.gamma(p["frailty_gamma_shape"], 1 / p["frailty_gamma_shape"]))
            anchor_age = int(rng.integers(18, 92))
            weight = round(float(rng.normal(80, 18)), 1)
            self.patients.append({
                "subject_id": subject_id, "gender": rng.choice(["F", "M"]),
                "anchor_age": anchor_age, "anchor_year": (first_in + shift).year,
                "anchor_year_group": group_label(first_in.year), "dod": None,
                "_frailty": frailty,
            })
            person = {"insurance": self.pick(INSURANCE), "language": self.pick(LANGUAGE),
                      "marital_status": self.pick(MARITAL_STATUS), "race": self.pick(RACE)}
            n_stays = 1 + min(3, int(rng.poisson(p["stays_per_patient_extra_mean"])))
            real_in = first_in
            for _ in range(n_stays):
                if real_in > REAL_END:
                    break
                los_days = float(np.clip(rng.lognormal(np.log(p["los_median_days"]),
                                                       p["los_sigma"]), 0.2, 60))
                real_out = real_in + timedelta(days=los_days)
                admit = real_in - timedelta(hours=self.u(0, 48))
                disch = real_out + timedelta(hours=self.u(2, 120))
                hadm += 1
                stay_id += 1
                stay = {"subject_id": subject_id, "hadm_id": hadm, "stay_id": stay_id,
                        "real_in": real_in, "real_out": real_out, "los_h": los_days * 24,
                        "shift": shift, "weight": weight}
                adm_type = str(rng.choice(
                    ["EW EMER.", "URGENT", "ELECTIVE", "SURGICAL SAME DAY ADMISSION"],
                    p=[0.6, 0.15, 0.15, 0.1]))
                self.admissions.append({
                    "subject_id": subject_id, "hadm_id": hadm,
                    "admittime": (admit + shift).strftime(FMT),
                    "dischtime": (disch + shift).strftime(FMT),
                    "deathtime": None, "admission_type": adm_type,
                    **person, **self.admission_details(adm_type, admit, real_in, shift),
                })
                self.stays.append({
                    "subject_id": subject_id, "hadm_id": hadm, "stay_id": stay_id,
                    "first_careunit": rng.choice(CAREUNITS),
                    "intime": (real_in + shift).strftime(FMT),
                    "outtime": (real_out + shift).strftime(FMT),
                    "los": round(los_days, 4),
                    "_real_in": real_in, "_real_out": real_out,
                })
                self.stays[-1]["last_careunit"] = self.stays[-1]["first_careunit"]
                self.simulate_stay(stay, frailty, group_label(real_in.year))
                # admittime can precede intime by up to 48 h; keep admissions from overlapping.
                real_in = disch + timedelta(hours=48, days=float(rng.exponential(180)))

    def pick(self, choices):
        values, probs = choices
        return values[self.fill.choice(len(values), p=probs)]

    def admission_details(self, adm_type, admit, real_in, shift):
        """Descriptive admissions columns; nothing downstream depends on them."""
        f = self.fill
        ed_reg = ed_out = None
        if f.random() < ED_VISIT_PROB.get(adm_type, 0.0):
            ed_reg = admit - timedelta(hours=float(f.uniform(2, 8)))
            ed_out = min(admit + timedelta(hours=float(f.uniform(0.5, 3))), real_in)
        return {
            "admit_provider_id": self.providers[f.integers(len(self.providers))],
            "admission_location": self.pick(ADMISSION_LOCATION[adm_type]),
            "discharge_location": self.pick(DISCHARGE_LOCATION),
            "edregtime": (ed_reg + shift).strftime(FMT) if ed_reg else None,
            "edouttime": (ed_out + shift).strftime(FMT) if ed_out else None,
            "hospital_expire_flag": 0,
        }

    def simulate_stay(self, stay, frailty, group):
        p, rng = self.p, self.rng
        los_h = stay["los_h"]
        need = min(1.0, p["plt_need_prob"] * frailty * p["period_multiplier"][group])
        plt_starts = []
        if rng.random() < need:
            onset = self.sample_onset(stay["real_in"], los_h)
            while onset is not None and onset < los_h:
                end = self.make_episode(stay, "platelets", onset)
                plt_starts.append(onset)
                if rng.random() >= p["plt_repeat_prob"]:
                    break
                onset = end + self.u(*p["repeat_gap_hours"])
        for prod in ("rbc", "ffp"):
            # Co-occurring episodes start within 12 h of a platelet episode,
            # drawn uniformly over the part of that window inside the stay.
            onsets = [self.u(max(0.0, s - 12), min(los_h, s + 12)) for s in plt_starts
                      if rng.random() < p[f"{prod}_given_plt_prob"]]
            if rng.random() < p[f"{prod}_indep_prob"]:
                t = self.sample_onset(stay["real_in"], los_h)
                if t is not None:
                    onsets.append(t)
            self.schedule_episodes(stay, prod, onsets)
        for prod in ("cryo", "albumin"):
            if rng.random() < p[f"{prod}_prob"]:
                t = self.sample_onset(stay["real_in"], los_h)
                if t is not None:
                    self.make_episode(stay, prod, t)
        if rng.random() < p["saline_prob"]:
            for _ in range(int(rng.integers(1, 6))):
                self.make_episode(stay, "saline", self.u(0, los_h * 0.999), n_bags=1)


def daily_truth(bags, stays):
    """Real-calendar daily bag counts and noon ICU census (what MIMIC hides)."""
    b = bags[bags["product"].isin(["platelets", "rbc", "ffp"])].copy()
    b["date"] = pd.to_datetime(b["real_start"]).dt.date
    demand = b.pivot_table(index="date", columns="product", values="bag_id",
                           aggfunc="count", fill_value=0)
    # Stays admitted late in 2019 can run into 2020; keep those bags.
    days = pd.date_range(REAL_START.date(), max(REAL_END.date(), b["date"].max()), freq="D")
    demand = demand.reindex(days.date, fill_value=0)
    noon = days + pd.Timedelta(hours=12)
    ins = np.sort(pd.to_datetime(stays["_real_in"]).values)
    outs = np.sort(pd.to_datetime(stays["_real_out"]).values)
    census = np.searchsorted(ins, noon.values) - np.searchsorted(outs, noon.values)
    demand["icu_census_noon"] = census
    demand.index.name = "real_date"
    return demand.reset_index()


def logseries_mle(mean):
    """Logseries theta whose mean, -theta / ((1 - theta) log(1 - theta)), equals `mean`."""
    if mean <= 1:
        return 0.0
    lo, hi = 1e-9, 1 - 1e-12
    for _ in range(100):
        theta = (lo + hi) / 2
        if -theta / ((1 - theta) * np.log(1 - theta)) < mean:
            lo = theta
        else:
            hi = theta
    return theta


def effective_targets(eps, dropped):
    """What a perfect Elston & Pickerel analysis of the observable data should recover."""
    days = pd.date_range(REAL_START.date(), REAL_END.date(), freq="D").date
    out = {}
    for prod, g in eps[eps["product"] != "saline"].groupby("product"):
        n = g["n_bags"]
        daily = pd.to_datetime(g["real_start"]).dt.date.value_counts().reindex(days, fill_value=0)
        out[prod] = {
            "episodes": int(len(g)),
            "episodes_per_day_mean": float(daily.mean()),
            "episodes_per_day_var": float(daily.var()),
            "bags_per_episode_mean": float(n.mean()),
            "logseries_theta_mle": logseries_mle(n.mean()),
            "share_truncated": float(g["truncated"].mean()),
            "share_delayed": float(g["delayed"].mean()),
            "candidates_dropped": int(dropped[prod]),
            "size_pmf": {str(k): float(v) for k, v in
                         n.value_counts(normalize=True).sort_index().items()},
        }
    return out


def duckdb_loader():
    """Load the CSVs as tables with MIMIC-IV's column types (auto-detection
    guesses wrong on columns that are always empty, like dod). Tables, not
    views: a view re-resolves its relative path against whatever directory
    it is later queried from."""
    lines = ["-- Run from the data directory: duckdb synth.duckdb < load_duckdb.sql"]
    for table, cols in SCHEMA.items():
        types = ", ".join(f"'{c}': '{t}'" for c, t in cols)
        lines.append(f"CREATE OR REPLACE TABLE {table.split('/')[1]} AS SELECT * FROM "
                     f"read_csv('{table}.csv.gz', header = true, columns = {{{types}}});")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--out", default="synth")
    ap.add_argument("--patients", type=int, default=50_000)
    ap.add_argument("--seed", type=int, default=None,
                    help="omit for hidden random parameters")
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    params = draw_params(rng)
    g = Generator(rng, params)
    g.run(args.patients)

    hosp, icu, key = (os.path.join(args.out, d) for d in ("hosp", "icu", "answer_key"))
    for d in (hosp, icu, key):
        os.makedirs(d, exist_ok=True)

    patients = pd.DataFrame(g.patients)
    stays = pd.DataFrame(g.stays)
    bags = pd.DataFrame(g.bags)

    gz = dict(index=False, compression="gzip")

    def write_table(df, table):
        df[[c for c, _ in SCHEMA[table]]].to_csv(os.path.join(args.out, f"{table}.csv.gz"), **gz)

    write_table(patients, "hosp/patients")
    write_table(pd.DataFrame(g.admissions), "hosp/admissions")
    write_table(stays, "icu/icustays")
    write_table(pd.DataFrame(D_ITEMS, columns=[c for c, _ in SCHEMA["icu/d_items"]]), "icu/d_items")
    rows = pd.DataFrame(g.rows).sample(frac=1, random_state=0)  # no helpful ordering
    write_table(rows, "icu/inputevents")
    with open(os.path.join(args.out, "load_duckdb.sql"), "w") as f:
        f.write(duckdb_loader())

    # ----- answer key -----
    with open(os.path.join(key, "true_params.json"), "w") as f:
        json.dump({"seed": args.seed, "n_patients": args.patients, **params}, f, indent=2)
    for col in ("real_start", "shifted_start"):
        bags[col] = pd.to_datetime(bags[col]).dt.strftime(FMT)
    bags.to_csv(os.path.join(key, "bags.csv.gz"), **gz)
    eps = pd.DataFrame(g.episodes)
    with open(os.path.join(key, "effective_targets.json"), "w") as f:
        json.dump(effective_targets(eps, g.dropped), f, indent=2)
    eps["real_start"] = pd.to_datetime(eps["real_start"]).dt.strftime(FMT)
    eps.to_csv(os.path.join(key, "episodes.csv.gz"), **gz)
    pd.DataFrame(g.row_key).to_csv(os.path.join(key, "row_key.csv.gz"), **gz)
    real = stays[["stay_id", "subject_id", "_real_in", "_real_out"]].rename(
        columns={"_real_in": "real_intime", "_real_out": "real_outtime"})
    real = real.merge(patients[["subject_id", "_frailty"]].rename(
        columns={"_frailty": "frailty"}), on="subject_id")
    for col in ("real_intime", "real_outtime"):
        real[col] = pd.to_datetime(real[col]).dt.strftime(FMT)
    real.to_csv(os.path.join(key, "stays_real_time.csv.gz"), **gz)
    daily_truth(bags, stays).to_csv(os.path.join(key, "true_daily_demand.csv.gz"), **gz)

    with open(os.path.join(key, "README.md"), "w") as f:
        f.write(ANSWER_KEY_README)
    with open(os.path.join(args.out, "README.md"), "w") as f:
        f.write(DATA_README)

    print(f"Wrote {len(patients):,} patients, {len(stays):,} ICU stays, "
          f"{len(rows):,} inputevents rows to {args.out}/")
    print(f"Answer key sealed in {key}/ (don't peek).")


DATA_README = """# Synthetic MIMIC-IV-shaped transfusion data

Five MIMIC-IV tables, with every column, in MIMIC-IV order and with
MIMIC-IV types (from mimic-code's buildmimic/postgres/create.sql). Coded
values follow the MIMIC-IV v2.2 demo: amountuom is "ml", ordercategoryname
is "07-Blood Products", care units have their full names, and so on. Item IDs
are synthetic, in the 990xxx range:

- hosp/patients.csv.gz, hosp/admissions.csv.gz
- icu/icustays.csv.gz, icu/d_items.csv.gz, icu/inputevents.csv.gz

Dates are shifted per patient into the 2110s-2190s, preserving day of week.
anchor_year_group gives the real 3-year period of each patient's first stay.

Load into DuckDB with MIMIC-IV's column types:
    cd synth && duckdb synth.duckdb < load_duckdb.sql

Known differences from real MIMIC-IV: times carry seconds (MIMIC-IV rounds
to the minute); nobody dies, so dod and deathtime are empty; admissions uses
4 of the 9 admission_type values; descriptive columns (race, insurance, ED
times, ...) are random filler with realistic values.

The data contains deliberate recording problems, just like real EHR data.
Finding them is part of the exercise. answer_key/ holds the truth; open it
only to grade a finished phase.
"""

ANSWER_KEY_README = """# Answer key (spoilers)

- true_params.json: every generating parameter. Demand departs from Elston &
  Pickerel on purpose (frailty, a heavy tail on platelet sizes, episodes cut
  short at ICU discharge), so a perfect E&P fit will NOT land on these
  numbers. Use them to explain the gap, not to grade.
- effective_targets.json: what a perfect analysis of the observable data
  should recover, per product: episodes per real calendar day (mean and
  variance), bags per episode, the logseries theta fitted to the true episode
  sizes, the size distribution, the share of episodes truncated or delayed,
  and candidate episodes dropped. Grade Phase 2 fits against this.
- bags.csv.gz: one row per true bag. Grade challenges 2-3 (bag counts per stay/product).
- episodes.csv.gz: true episodes. n_bags is the bags actually given;
  n_intended is the size drawn before the episode was cut short at ICU
  discharge (truncated = n_bags < n_intended). delayed = the episode was
  pushed back to keep it 12 h clear of the previous episode of that product.
  For every product except saline, within one stay:
    - consecutive bags of an episode are 0-2 h apart (previous bag's last
      row ends -> next bag starts; bags never overlap);
    - episodes are at least 12 h apart; repeat and delayed episodes start
      12-72 h after the previous episode's last bag ends.
  So any threshold strictly between 2 and 12 h recovers episodes exactly,
  whether the gap is measured from LAG(endtime) or a running max. Saline
  bags are scattered single-bag episodes and may overlap.
- row_key.csv.gz: per orderid -> bag_id, is_valid (False = Rewritten row to drop),
  duplicated (an exact copy exists), traps (split, stopped, rewritten,
  legacy_units, late_storetime).
- stays_real_time.csv.gz: unshifted ICU times and each patient's frailty.
- true_daily_demand.csv.gz: real-calendar daily bags by product plus noon ICU
  census, running a few days into 2020 for stays that cross the new year.
  This is the series MIMIC-style date shifting makes impossible to build.

Counting rules used by the generator:
- A bag is one infused unit. Split rows (same linkorderid, Paused then
  FinishedRunning) are one bag. A Stopped row is still one (partial) bag.
- Legacy item 990102 records donor units (4-6 per bag); each valid row is one bag.
- Rewritten rows are invalid; exact duplicates count once.
- Cryoprecipitate, albumin and saline are not platelets.
"""

if __name__ == "__main__":
    main()
