"""Static curriculum definitions for supported Cornell undergraduate minors.

All course codes and track rules are sourced from official Cornell department
curriculum pages and registrar minor guides:
- Law & Society: philosophy.cornell.edu/law-society-courses
- Business (General, BME, DBMLS): business.cornell.edu/programs/*
- Inequality Studies (+ Health Equity Track): inequality.cornell.edu/*
- Labor & Social Justice: ilr.cornell.edu / courses.cornell.edu (ILRGL 15 cr)
- History: history.cornell.edu/undergraduate
- Information Science: infosci.cornell.edu/information-science-minor
- Psychology: psychology.cornell.edu/minor & /major
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Cornell department renames so historical minor lists match current Class Roster codes.
SUBJECT_ALIASES: dict[str, tuple[str, ...]] = {
    "PAM": ("PAM", "PUBPOL"),
    "PUBPOL": ("PUBPOL", "PAM"),
    "DSOC": ("DSOC", "GDEV"),
    "GDEV": ("GDEV", "DSOC"),
    "ILRIC": ("ILRIC", "ILRGL"),
    "ILRLR": ("ILRLR", "ILRGL"),
    "ILRGL": ("ILRGL", "ILRIC", "ILRLR"),
}


@dataclass(frozen=True)
class MinorCollegeDef:
    """College-specific curriculum variant for a minor (e.g., A&S/CALS vs Engineering vs Hotel)."""

    id: str
    label: str
    short_label: str
    total_required_summary: str
    note: str


@dataclass(frozen=True)
class MinorCategoryDef:
    """One completable requirement category or part inside a minor track."""

    id: str
    label: str
    short_label: str
    required_summary: str
    rule_summary: str
    tone: str  # emerald | sky | violet | amber | teal | rose | indigo
    courses: frozenset[str] = frozenset()
    wildcard_courses: frozenset[str] = frozenset()
    dynamic_rule: Optional[str] = None
    required_count: Optional[int] = None
    required_credits: Optional[float] = None


@dataclass(frozen=True)
class MinorVersionDef:
    """Specific curriculum version, track, or concentration for a minor."""

    id: str
    label: str
    short_label: str
    description: str
    total_required_summary: str
    categories: tuple[MinorCategoryDef, ...]


@dataclass(frozen=True)
class MinorDef:
    """Top-level undergraduate minor definition."""

    id: str
    label: str
    short_label: str
    department: str
    default_version: str
    overview: str
    versions: tuple[MinorVersionDef, ...]
    default_college: str = ""
    colleges: tuple[MinorCollegeDef, ...] = ()


# ---------------------------------------------------------------------------
# 1. Law & Society (philosophy.cornell.edu/law-society-courses)
# ---------------------------------------------------------------------------

_LS_WILDCARD = frozenset({"PHIL 2990"})

_LS_CAT1_LEGAL_INSTITUTIONS = frozenset({
    "AEM 2300", "ALS 4998", "AMST 2669", "AMST 3033", "AMST 3071", "AMST 3072",
    "AMST 3112", "AMST 3121", "AMST 3122", "AMST 3131", "AMST 3161", "AMST 3180",
    "AMST 3425", "AMST 4252", "AMST 4998", "CAPS 4998", "DSOC 4800", "ECON 2300",
    "ECON 3255", "EDUC 3142", "FGSS 2010", "GDEV 4800", "GOVT 1313", "GOVT 2012",
    "GOVT 2283", "GOVT 2665", "GOVT 3001", "GOVT 3032", "GOVT 3052", "GOVT 3071",
    "GOVT 3072", "GOVT 3112", "GOVT 3121", "GOVT 3122", "GOVT 3131", "GOVT 3150",
    "GOVT 3161", "GOVT 3242", "GOVT 3281", "GOVT 3431", "GOVT 4218", "GOVT 4998",
    "HADM 4850", "HD 3330", "HIST 1600", "HIST 1631", "HIST 2163", "HIST 2422",
    "HIST 2815", "HIST 3180", "HIST 3435", "HIST 4030", "HIST 4252", "HIST 4945",
    "ILRGL 2010", "ILRGL 3875", "ILRGL 4033", "ILRGL 4842", "ILRGL 4890",
    "ILRLR 2010", "ILRLR 3875", "ILRLR 4033", "ILRLR 4842", "ILRLR 4890",
    "LAW 3281", "LAW 3920", "LAW 4041", "LAW 4122", "LAW 4131", "LAW 4443",
    "LAW 5021", "NTRES 4750", "PADM 3172", "PADM 3730", "PUBPOL 2301",
    "PUBPOL 3172", "PUBPOL 3270", "PUBPOL 3330", "PUBPOL 3600", "PUBPOL 3730",
    "PUBPOL 4060", "PUBPOL 4640", "SOC 4240",
})

_LS_CAT2_LAW_POLICY = frozenset({
    "AEM 3557", "AEM 4450", "ALS 4998", "AMST 1951", "AMST 2152", "AMST 2225",
    "AMST 2710", "AMST 2817", "AMST 3033", "AMST 3065", "AMST 3092", "AMST 3121",
    "AMST 3141", "AMST 3142", "AMST 3149", "AMST 3155", "AMST 3800", "AMST 3870",
    "AMST 3911", "AMST 4435", "AMST 4850", "AMST 4851", "AMST 4998", "ANTHR 3552",
    "ASIAN 3305", "ASIAN 3365", "BSOC 3311", "CAPS 3000", "CAPS 3140", "CAPS 3857",
    "CAPS 4998", "COML 4575", "COMM 4201", "CRP 2010", "CRP 3430", "CRP 3720",
    "CRP 3850", "CRP 4330", "CRP 5330", "DSOC 2090", "DSOC 2200", "DSOC 2220",
    "DSOC 2710", "DSOC 2750", "DSOC 3040", "DSOC 3240", "DSOC 3700", "DSOC 4312",
    "ECON 3610", "ECON 3670", "ECON 3805", "ECON 3830", "ECON 3850", "ECON 4260",
    "ECON 4410", "ECON 4904", "ECON 4906", "EDUC 2710", "EDUC 3143", "ENVS 4330",
    "GDEV 2090", "GDEV 2200", "GDEV 2220", "GDEV 2710", "GDEV 2750", "GDEV 3040",
    "GDEV 3240", "GDEV 3280", "GDEV 3311", "GDEV 3700", "GDEV 4312", "GDEV 4450",
    "GOVT 1817", "GOVT 2152", "GOVT 2225", "GOVT 2817", "GOVT 3032", "GOVT 3042",
    "GOVT 3087", "GOVT 3091", "GOVT 3092", "GOVT 3121", "GOVT 3141", "GOVT 3142",
    "GOVT 3152", "GOVT 3303", "GOVT 3557", "GOVT 3735", "GOVT 3777", "GOVT 3857",
    "GOVT 3867", "GOVT 3999", "GOVT 4112", "GOVT 4435", "GOVT 4998", "GOVT 6021",
    "HADM 4800", "HADM 4810", "HADM 4890", "HADM 6800", "HIST 1951", "HIST 2423",
    "HIST 3140", "HIST 3391", "HIST 3870", "HIST 4850", "HIST 4851",
    "ILRGL 2215", "ILRGL 2280", "ILRGL 2810", "ILRGL 3020", "ILRGL 3035",
    "ILRGL 3045", "ILRGL 3047", "ILRGL 3065", "ILRGL 3557", "ILRGL 3810",
    "ILRGL 3870", "ILRGL 4012", "ILRGL 4022", "ILRGL 4040", "ILRGL 4060",
    "ILRGL 4312", "ILRGL 4330", "ILRGL 4333", "ILRGL 4340", "ILRGL 4344",
    "ILRGL 4360", "ILRGL 6045", "ILRGL 6080", "ILROB 2220", "ILRST 2150",
    "INFO 4200", "INFO 4940", "LATA 1951", "LATA 3065", "LAW 4021", "LAW 4081",
    "LAW 4121", "LAW 4330", "LAW 6024", "LAW 6344", "LSP 2152", "LSP 2200",
    "LSP 3065", "LSP 3810", "LSP 4312", "LSP 4850", "LSP 4851", "NS 4450",
    "NS 4998", "NTRES 3311", "NTRES 4300", "NTRES 4340", "PHIL 1950",
    "PUBPOL 2040", "PUBPOL 2208", "PUBPOL 2220", "PUBPOL 2250", "PUBPOL 2300",
    "PUBPOL 2350", "PUBPOL 2810", "PUBPOL 3032", "PUBPOL 3040", "PUBPOL 3041",
    "PUBPOL 3090", "PUBPOL 3110", "PUBPOL 3130", "PUBPOL 3200", "PUBPOL 3280",
    "PUBPOL 3340", "PUBPOL 3360", "PUBPOL 3400", "PUBPOL 3410", "PUBPOL 3620",
    "PUBPOL 3670", "PUBPOL 3680", "PUBPOL 3710", "PUBPOL 3764", "PUBPOL 3810",
    "PUBPOL 4060", "PUBPOL 4470", "PUBPOL 4960", "PUBPOL 5130", "PUBPOL 5451",
    "PUBPOL 5680", "PUBPOL 6140", "SOC 2070", "SOC 2208", "SOC 2220", "SOC 2710",
    "SOC 3040", "SOC 3240", "SOC 3360", "SOC 3380", "SOC 3570", "SOC 3620",
    "SOC 3710", "SOC 3770", "SOC 3810", "SOC 3820", "SOC 4470", "SOC 4520",
    "SOC 6140", "STS 3241", "STS 3311", "STS 3911", "STS 4200",
})

_LS_CAT3_LAW_SOCIAL_STRUCTURE = frozenset({
    "AAS 2130", "AAS 2641", "AAS 3885", "AEM 2300", "AMST 1104", "AMST 1595",
    "AMST 1951", "AMST 2640", "AMST 2645", "AMST 2682", "AMST 2730", "AMST 2810",
    "AMST 2980", "AMST 3012", "AMST 3024", "AMST 3231", "AMST 3420", "AMST 3550",
    "AMST 3590", "AMST 3621", "AMST 3785", "AMST 3854", "AMST 3885", "AMST 4051",
    "ANTHR 2433", "ANTHR 2437", "ANTHR 2468", "ANTHR 3475", "ASIAN 2280",
    "ASIAN 3304", "ASIAN 3396", "ASIAN 4415", "ASRC 1595", "ASRC 2641",
    "ASRC 3206", "ASRC 3590", "ASRC 3626", "ASRC 3947", "BSOC 2201", "BSOC 2468",
    "BSOC 4127", "CAPS 2132", "CAPS 3049", "CAPS 4127", "COML 3541", "COML 3743",
    "COML 4250", "COMM 3250", "CRP 2010", "CRP 3854", "DSOC 3050", "DSOC 3550",
    "DSOC 3750", "ECE 2980", "ECON 2300", "ECON 3440", "ECON 3485", "ENGL 3206",
    "ENGL 3920", "ENGRG 2980", "FGSS 2024", "FGSS 2290", "FGSS 2468", "FGSS 2490",
    "FGSS 2730", "FGSS 3000", "FGSS 3206", "FGSS 3400", "FGSS 3520", "FGSS 3680",
    "FGSS 4035", "FGSS 4127", "FGSS 4460", "FGSS 4491", "FGSS 4650", "FREN 3520",
    "GDEV 2201", "GDEV 3010", "GDEV 3050", "GDEV 3280", "GDEV 3550", "GDEV 3750",
    "GERST 3620", "GERST 4250", "GOVT 2240", "GOVT 2935", "GOVT 2947", "GOVT 3012",
    "GOVT 3043", "GOVT 3044", "GOVT 3051", "GOVT 3303", "GOVT 3401", "GOVT 3494",
    "GOVT 3636", "GOVT 3685", "GOVT 3785", "GOVT 3937", "GOVT 3947", "GOVT 4232",
    "GOVT 4735", "HD 4140", "HIST 1595", "HIST 1951", "HIST 2132", "HIST 2521",
    "HIST 2640", "HIST 2641", "HIST 2680", "HIST 2730", "HIST 2920", "HIST 3231",
    "HIST 3590", "HIST 3680", "HIST 3884", "HIST 3960", "HIST 4127", "HIST 4950",
    "HORT 2240", "ILRGL 1200", "ILRGL 2060", "ILRGL 2210", "ILRGL 2215",
    "ILRGL 2310", "ILRGL 2390", "ILRGL 2810", "ILRGL 3315", "ILRGL 3885",
    "ILRGL 4035", "ILRGL 4325", "ILRGL 4330", "ILRGL 6079", "ILRLE 3460",
    "ILRLE 4450", "INFO 2921", "JWST 3655", "LATA 1951", "LAW 4031", "LAW 4051",
    "LGBT 2290", "LSP 1104", "LSP 2810", "LSP 3250", "NES 3655", "NTRES 2201",
    "PHIL 1930", "PHIL 2490", "PHIL 2945", "PHIL 2965", "PHIL 3470", "PHIL 4490",
    "PSYCH 2120", "PUBPOL 2030", "PUBPOL 2370", "PUBPOL 2810", "PUBPOL 3020",
    "PUBPOL 3050", "PUBPOL 3230", "PUBPOL 3250", "PUBPOL 3260", "PUBPOL 3280",
    "PUBPOL 3620", "PUBPOL 3810", "PUBPOL 4160", "PUBPOL 4600", "RELST 3680",
    "SHUM 2437", "SHUM 3520", "SHUM 3620", "SHUM 3636", "SHUM 3655", "SHUM 4655",
    "SHUM 4800", "SOC 1104", "SOC 2030", "SOC 2150", "SOC 2370", "SOC 2560",
    "SOC 2810", "SOC 2930", "SOC 3250", "SOC 3620", "SOC 3810", "SOC 4160",
    "STS 2468", "STS 2920",
})

_LS_CAT4_LAW_CULTURE = frozenset({
    "AAS 2100", "AAS 2130", "AEM 2350", "AEM 2805", "AEM 3388", "AIIS 2420",
    "AMST 2640", "AMST 2682", "AMST 2686", "AMST 3145", "AMST 3510", "AMST 3590",
    "AMST 3762", "AMST 3777", "AMST 3911", "AMST 4021", "AMST 4301", "ANTHR 2410",
    "ANTHR 2420", "ANTHR 2468", "ANTHR 3428", "ANTHR 3762", "ANTHR 3777",
    "ASIAN 2247", "ASIAN 3304", "ASIAN 3334", "ASIAN 3380", "ASIAN 4454",
    "ASRC 2670", "ASRC 3353", "ASRC 3590", "BSOC 2420", "BSOC 2468", "CAPS 3049",
    "CAPS 3387", "CAPS 4049", "CLASS 2806", "COGST 3190", "COML 3300", "COMM 3140",
    "COMM 4201", "CRP 4440", "DSOC 3290", "ECON 3300", "ECON 3710", "ECON 3800",
    "ECON 4040", "ENGL 3762", "ENGL 3778", "ENGL 3781", "ENGL 3941", "FGSS 2468",
    "FGSS 2806", "GDEV 3290", "GERST 3550", "GOVT 2264", "GOVT 2673", "GOVT 2747",
    "GOVT 2806", "GOVT 2977", "GOVT 3042", "GOVT 3044", "GOVT 3091", "GOVT 3221",
    "GOVT 3284", "GOVT 3293", "GOVT 3294", "GOVT 3313", "GOVT 3353", "GOVT 3384",
    "GOVT 3443", "GOVT 3512", "GOVT 3633", "GOVT 3683", "GOVT 3705", "GOVT 3766",
    "GOVT 3805", "GOVT 4021", "HD 2650", "HD 3190", "HD 4230", "HIST 2159",
    "HIST 2640", "HIST 2672", "HIST 2674", "HIST 2680", "HIST 2686", "HIST 3519",
    "HIST 3590", "HIST 4360", "HIST 4662", "HIST 4751", "ILRGL 2390", "ILRGL 3071",
    "ILRGL 3380", "ILRGL 4075", "ILRGL 4880", "ILRLE 3440", "INFO 4200",
    "INFO 4250", "INFO 6210", "JWST 2159", "JWST 2674", "JWST 2686", "JWST 2697",
    "JWST 3732", "JWST 3767", "JWST 3805", "JWST 4013", "LATA 3290", "LAW 2650",
    "LAW 4013", "LING 2223", "LSP 3762", "LSP 3777", "NES 2670", "NES 2674",
    "NES 2686", "NES 2697", "NES 3519", "NES 3550", "NES 3732", "NES 3767",
    "NES 3805", "NTRES 4440", "PMA 3490", "PSYCH 2650", "PSYCH 3190", "PUBPOL 3140",
    "PUBPOL 3230", "PUBPOL 3460", "PUBPOL 3510", "PUBPOL 3620", "PUBPOL 4280",
    "RELST 2247", "RELST 3734", "SHUM 2101", "SHUM 2247", "SOC 2480", "SOC 3620",
    "SOC 3680", "SOC 3760", "STS 2468", "STS 3042", "STS 3911", "STS 4200",
    "STS 4751",
})

_LS_CAT5_LAW_ETHICS = frozenset({
    "AEM 3205", "AMST 3072", "AMST 4655", "ANSC 4140", "ANSC 5140", "ANTHR 2468",
    "BSOC 2051", "BSOC 2061", "BSOC 2468", "BSOC 4650", "CLASS 1665",
    "COGST 2415", "COGST 3135", "COGST 4940", "COMM 4300", "CS 1340", "DEA 4800",
    "ECE 2750", "ENGL 4020", "ENGRG 2750", "ENGRG 3600", "ENGRG 3605", "FGSS 2468",
    "FSAD 4800", "GDEV 2202", "GOVT 2432", "GOVT 2605", "GOVT 2897", "GOVT 3022",
    "GOVT 3072", "GOVT 3087", "GOVT 3625", "GOVT 3626", "GOVT 3887", "GOVT 4655",
    "HD 2620", "HD 4940", "ILRGL 3342", "ILRGL 3830", "ILRGL 4075", "ILRGL 4820",
    "ILROB 4760", "INFO 1200", "INFO 1260", "INFO 2750", "INFO 4270", "INFO 4301",
    "INFO 4940", "LAW 3290", "LAW 3887", "LAW 4081", "LAW 7072", "NAVS 4402",
    "NTRES 3320", "NTRES 4330", "PHIL 1410", "PHIL 1440", "PHIL 1450", "PHIL 1960",
    "PHIL 2410", "PHIL 2415", "PHIL 2420", "PHIL 2430", "PHIL 2450", "PHIL 2455",
    "PHIL 2960", "PHIL 3460", "PHIL 3475", "PHIL 3480", "PHIL 3915", "PHIL 4470",
    "PSYCH 2415", "PSYCH 2620", "PSYCH 3135", "PSYCH 4940", "PUBPOL 3200",
    "PUBPOL 3830", "PUBPOL 4210", "PUBPOL 5520", "SHUM 2455", "SHUM 3475",
    "SOC 4430", "STS 1201", "STS 2051", "STS 2061", "STS 2451", "STS 2468",
    "STS 2751", "STS 3601", "STS 4650",
})


# ---------------------------------------------------------------------------
# 2. Business (business.cornell.edu/programs/business-minor/, -engineers/, -life-sciences/)
# ---------------------------------------------------------------------------

_BUS_MICRO = frozenset({"ECON 1110", "ECON 3030", "PUBPOL 2000"})
_BUS_MGMT = frozenset({"AEM 1200", "HADM 1810", "ILRID 1700", "NCC 5540"})
_BUS_MKTG = frozenset({"AEM 2400", "HADM 2410", "NCC 5530", "NCC 4530"})
_BUS_ACCT = frozenset({"AEM 2210", "HADM 2230", "NCC 5500"})
_BUS_ACCT_BME = frozenset({"AEM 2210", "HADM 2230", "NCC 5500", "ORIE 3150"})
_BUS_FIN = frozenset({"AEM 2241", "AEM 5241", "HADM 2250", "NCC 5560"})
_BUS_GENERAL_CAPSTONE = frozenset({"AEM 4940", "AEM 4660", "AEM 4665"})
_BUS_BME_INTRO = _BUS_MGMT | _BUS_MKTG | frozenset({"NCC 5580"})
_BUS_BME_CAPSTONE = frozenset({"AEM 4660"})
_BUS_DBMLS_MGMT_MKTG = _BUS_MGMT | _BUS_MKTG
_BUS_DBMLS_CAREER = frozenset({
    "AEM 1600", "AEM 2011", "AEM 2220", "AEM 3110", "AEM 3205", "AEM 3230",
    "AEM 3249", "AEM 3251", "AEM 3310", "AEM 4190", "AEM 4355", "AEM 4485",
    "GDEV 3280", "NBA 5070", "NBA 6650", "NBA 6720", "NCC 5540",
    "PUBPOL 2350", "PUBPOL 3110", "PUBPOL 3280", "PUBPOL 5630",
})
_BUS_DBMLS_CAPSTONE = frozenset({"AEM 4661"})


# ---------------------------------------------------------------------------
# 3. Inequality Studies (inequality.cornell.edu SP27 + FA26 + HET)
# ---------------------------------------------------------------------------

_INEQ_CORE = frozenset({"SOC 2208", "AMST 2208", "PUBPOL 2208"})
_INEQ_OVERVIEW = frozenset({
    "AMST 2070", "AMST 2225", "AMST 2365", "GDEV 3700", "GOVT 2225", "ILROB 2220",
    "PHIL 1950", "PUBPOL 2220", "PUBPOL 2250", "PUBPOL 2370", "SOC 2070",
    "SOC 2220", "SOC 2370", "SOC 3710",
})
_INEQ_HET_ELECTIVES = frozenset({
    "AEM 1600", "AEM 4485", "AEM 6485", "ANTHR 2424", "ANTHR 2468", "BSOC 2051",
    "BSOC 2468", "BSOC 3111", "COGST 1500", "COGST 1501", "DEA 1500", "DEA 1501",
    "ECON 3720", "FGSS 2468", "GDEV 3020", "GDEV 3111", "GDEV 3280", "HD 2510",
    "HD 4240", "NS 1150", "NS 2450", "NS 2600", "NS 3060", "NS 4480", "NS 4500",
    "NS 4510", "NS 4600", "NS 6480", "NS 6500", "NS 6510", "PSYCH 1500",
    "PSYCH 1501", "PUBPOL 2050", "PUBPOL 2350", "PUBPOL 3180", "PUBPOL 3280",
    "PUBPOL 3650", "PUBPOL 4370", "PUBPOL 5370", "PUBPOL 5650", "SOC 2510",
    "SOC 3130", "SOC 3180", "SOC 4120", "STS 2051", "STS 2468", "STS 3111",
})
_INEQ_REG_ELECTIVES = frozenset({
    "AAS 1100", "AAS 2620", "AAS 3030", "AEM 2350", "AEM 3385", "AEM 4533",
    "AEM 6533", "AIIS 1100", "AIIS 1110", "AIIS 2600", "AIIS 4000", "AIIS 6000",
    "ALS 4998", "AMST 1101", "AMST 1290", "AMST 1500", "AMST 1595", "AMST 1600",
    "AMST 1601", "AMST 1802", "AMST 2023", "AMST 2070", "AMST 2220", "AMST 2225",
    "AMST 2251", "AMST 2256", "AMST 2353", "AMST 2365", "AMST 2401", "AMST 2600",
    "AMST 2620", "AMST 2650", "AMST 2669", "AMST 2682", "AMST 2710", "AMST 2955",
    "AMST 3121", "AMST 3131", "AMST 3355", "AMST 3405", "AMST 3420", "AMST 3430",
    "AMST 3445", "AMST 3703", "AMST 3715", "AMST 3754", "AMST 3808", "AMST 3815",
    "AMST 4051", "AMST 4160", "AMST 4998", "AMST 5710", "AMST 6703",
    "ANTHR 1700", "ANTHR 2400", "ANTHR 3402", "ANTHR 3405", "ANTHR 3703",
    "ANTHR 4458", "ANTHR 6703", "ANTHR 7458", "ASIAN 2930", "ASRC 1500",
    "ASRC 1595", "ASRC 1790", "ASRC 2023", "ASRC 2353", "ASRC 2680", "ASRC 2955",
    "ASRC 3350", "ASRC 4303", "ASRC 4561", "ASRC 4602", "ASRC 6303", "ASRC 6602",
    "BIONB 3215", "BSOC 2061", "BSOC 3311", "CAPS 4998", "COGST 3530",
    "COGST 4250", "COML 2400", "COML 3300", "COML 3743", "COML 4250", "COMM 3110",
    "COMM 4260", "COMM 4850", "CRP 3074", "CRP 3201", "CRP 3270", "CRP 3430",
    "CRP 4040", "CRP 4120", "CRP 5040", "CRP 5074", "CRP 6120", "CRP 6201",
    "CRP 6270", "ECON 3171", "ECON 3250", "ECON 3340", "ECON 3440", "ECON 3450",
    "ECON 3760", "ECON 3770", "ECON 3855", "ECON 4290", "ECON 4560", "EDUC 2200",
    "EDUC 2610", "EDUC 2710", "EDUC 3110", "EDUC 3405", "EDUC 4458", "EDUC 5710",
    "EDUC 7458", "ENGL 2400", "ENGL 2600", "ENGL 2620", "ENGL 2650", "ENGL 3950",
    "ENGL 3954", "FGSS 1940", "FGSS 2010", "FGSS 2023", "FGSS 2290", "FGSS 3000",
    "FGSS 3210", "FGSS 3320", "FGSS 3350", "FGSS 3400", "FGSS 3754", "FGSS 3820",
    "FGSS 4035", "FGSS 4260", "FGSS 4371", "FGSS 4458", "FGSS 4460", "FGSS 4491",
    "FGSS 4561", "FGSS 6371", "FGSS 7458", "GDEV 1300", "GDEV 2010", "GDEV 2100",
    "GDEV 2710", "GDEV 3010", "GDEV 3110", "GDEV 3311", "GDEV 3700", "GDEV 4120",
    "GDEV 5710", "GDEV 6120", "GDEV 6320", "GERST 3550", "GERST 4250", "GOVT 1503",
    "GOVT 2022", "GOVT 2225", "GOVT 2665", "GOVT 3121", "GOVT 3131", "GOVT 3303",
    "GOVT 3401", "GOVT 3583", "GOVT 3715", "GOVT 3977", "GOVT 4735", "GOVT 4998",
    "GOVT 6998", "HADM 4315", "HD 3110", "HD 3310", "HD 3320", "HD 3530",
    "HD 4250", "HD 4560", "HD 6560", "HIST 1595", "HIST 1802", "HIST 1930",
    "HIST 1970", "HIST 2023", "HIST 2220", "HIST 2251", "HIST 2353", "HIST 2655",
    "HIST 2680", "HIST 2955", "HIST 3430", "HIST 4303", "HIST 6303", "ILRGL 1200",
    "ILRGL 2010", "ILRGL 2210", "ILRGL 2350", "ILRGL 2390", "ILRGL 3020",
    "ILRGL 3315", "ILRGL 3815", "ILRGL 3820", "ILRGL 4035", "ILRGL 4325",
    "ILRGL 4330", "ILRGL 4347", "ILRGL 4842", "ILRGL 4865", "ILRGL 5815",
    "ILRGL 6325", "ILRGL 6347", "ILRGL 6840", "ILRGL 6865", "ILRID 2510",
    "ILRID 2610", "ILRLE 2400", "ILRLE 3445", "ILRLE 3550", "ILRLE 4426",
    "ILRLE 4440", "ILRLE 4450", "ILROB 2220", "ILROB 3270", "ILROB 4710",
    "ILROB 6715", "INFO 4505", "INFO 5505", "JWST 3655", "LATA 1802",
    "LATA 1970", "LAW 4051", "LAW 4131", "LAW 6533", "LGBT 1940", "LGBT 2290",
    "LGBT 3210", "LGBT 3754", "LING 2221", "LSP 1802", "LSP 2251", "LSP 2400",
    "LSP 3405", "LSP 3754", "NES 3655", "NES 6655", "NS 4998", "NTRES 3311",
    "NTRES 6310", "PHIL 1950", "PHIL 2410", "PHIL 2960", "PHIL 4490",
    "PHIL 6490", "PLSCI 1300", "PLSCI 2100", "PMA 3490", "PMA 3754",
    "PSYCH 4560", "PUBPOL 2030", "PUBPOL 2040", "PUBPOL 2210", "PUBPOL 2220",
    "PUBPOL 2250", "PUBPOL 2370", "PUBPOL 3080", "PUBPOL 3151", "PUBPOL 3231",
    "PUBPOL 3550", "PUBPOL 3583", "PUBPOL 3810", "PUBPOL 4060", "PUBPOL 4101",
    "PUBPOL 4160", "PUBPOL 5060", "PUBPOL 5080", "PUBPOL 5151", "PUBPOL 5230",
    "PUBPOL 5610", "SHUM 1802", "SHUM 1930", "SHUM 2023", "SHUM 2220",
    "SHUM 2650", "SHUM 3655", "SHUM 4202", "SOC 1101", "SOC 1290", "SOC 2030",
    "SOC 2070", "SOC 2202", "SOC 2220", "SOC 2250", "SOC 2370", "SOC 2560",
    "SOC 2710", "SOC 3190", "SOC 3650", "SOC 3710", "SOC 3750", "SOC 3800",
    "SOC 3810", "SOC 4160", "SOC 4370", "SOC 5710", "SOC 6370", "STS 2023",
    "STS 2061", "STS 3311",
})
_INEQ_ALL_ELECTIVES = _INEQ_HET_ELECTIVES | _INEQ_REG_ELECTIVES


# ---------------------------------------------------------------------------
# 6. Information Science (infosci.cornell.edu + concentration checklists)
# ---------------------------------------------------------------------------

_IS_CORE_ALL = frozenset({
    "INFO 1200", "STS 1201",
    "INFO 1260", "CS 1340",
    "INFO 1300",
    "INFO 2040", "CS 2850", "ECON 2040", "SOC 2090", "INFO 2850",
    "INFO 2450", "COMM 2450",
    "INFO 2950", "INFO 2951",
})

_IS_BEHAVIORAL = frozenset({
    "INFO 2450", "COMM 2450",
    "INFO 3170", "INFO 3200", "COMM 3200", "INFO 3300", "INFO 3450", "COMM 3450",
    "INFO 3720", "INFO 3950", "INFO 4100", "INFO 4140", "INFO 4240",
    "INFO 4300", "CS 4300", "INFO 4350", "INFO 4360", "INFO 4430",
    "INFO 4450", "COMM 4450", "INFO 4490", "INFO 4500", "INFO 4505",
    "COMM 4380", "COMM 4940", "CS 3780", "CS 4740", "CS 4780", "PSYCH 3800",
    "INFO 4940",
})

_IS_DATA_SCIENCE = frozenset({
    "INFO 2950", "INFO 2951", "COMM 3190", "SOC 4390",
    "INFO 3130", "INFO 3300", "INFO 3312", "INFO 3350", "INFO 3370",
    "INFO 3720", "INFO 3950", "INFO 4100", "INFO 4300", "CS 4300",
    "INFO 4310", "INFO 4350", "CS 3780", "CS 4320", "CS 4740", "CS 4780",
    "CS 4786", "ORIE 3500", "ORIE 3741", "ORIE 4740", "STSCI 3740", "STSCI 4060",
    "STSCI 4520", "STSCI 4740", "INFO 4940",
})

_IS_DIGITAL_CULTURE = frozenset({
    "COMM 3190", "INFO 1340", "ENGL 1340", "INFO 1350",
    "INFO 2921", "HIST 2920", "STS 2921", "ENGRG 2980", "AMST 2980",
    "INFO 3200", "COMM 3200", "INFO 3560", "INFO 3561", "ANTHR 3061", "COMM 3560",
    "STS 3561", "VISST 3560", "INFO 3660", "INFO 4140", "INFO 4260", "INFO 4270",
    "INFO 4940",
})

_IS_ETHICS_LAW = frozenset({
    "INFO 1200", "STS 1201", "INFO 1260", "CS 1340",
    "COMM 3190", "COMM 4010", "COMM 4300", "INFO 4301", "COMM 4940",
    "INFO 2750", "ENGRG 2750", "ECE 2750", "STS 2751",
    "INFO 3200", "COMM 3200", "INFO 3210", "INFO 4113", "INFO 4140",
    "INFO 4145", "INFO 4200", "STS 4200", "COMM 4201",
    "INFO 4210", "PUBPOL 4210", "INFO 4240", "INFO 4250", "INFO 4260",
    "INFO 4270", "INFO 4390", "INFO 4561", "INFO 4940",
})

_IS_INTERACTIVE_TECH = frozenset({
    "INFO 1300", "INFO 2300", "INFO 2310", "INFO 3152", "CS 3152",
    "INFO 3160", "INFO 4120", "INFO 4152", "CS 4152",
    "INFO 4320", "INFO 4345", "INFO 4410", "INFO 4470",
    "CS 3780", "CS 4620", "CS 4758", "INFO 4940",
})

_IS_NETWORKS_MARKETS = frozenset({
    "INFO 2040", "CS 2850", "ECON 2040", "SOC 2090", "INFO 2850",
    "COMM 3150", "COMM 4940",
    "ECON 3810", "ECON 3825", "ECON 4020", "ECON 4610", "ECON 4620",
    "INFO 4220", "CS 4852", "INFO 6220", "INFO 4360",
    "ORIE 3200", "ORIE 4350", "ORIE 4740",
    "CS 3780", "CS 4740", "CS 4780",
    "INFO 3300", "INFO 3950", "INFO 4100", "INFO 4300", "CS 4300",
    "INFO 4350", "SOC 4200", "INFO 4940",
})

_IS_UX = frozenset({
    "INFO 1300", "INFO 2310", "INFO 2450", "COMM 2450",
    "INFO 3450", "COMM 3450", "INFO 3560", "INFO 3561",
    "INFO 4240", "INFO 4400", "COMM 4400", "INFO 4410",
    "INFO 4420", "INFO 4470", "INFO 4940",
})

_IS_ALL_CONCENTRATION_COURSES = (
    _IS_BEHAVIORAL
    | _IS_DATA_SCIENCE
    | _IS_DIGITAL_CULTURE
    | _IS_ETHICS_LAW
    | _IS_INTERACTIVE_TECH
    | _IS_NETWORKS_MARKETS
    | _IS_UX
)

_IS_HOTEL_REQUIRED = frozenset({"HADM 3740", "HADM 4760"})
_IS_HOTEL_EXTRA_ELECTIVES = frozenset({"AEM 3220"})

INFO_SCIENCE_COLLEGES: tuple[MinorCollegeDef, ...] = (
    MinorCollegeDef(
        id="as_cals",
        label="Arts & Sciences / CALS / Other (6 courses)",
        short_label="A&S / CALS (6)",
        total_required_summary="6 courses (1 Core + 3 Conc + 2 Elec)",
        note=(
            "A&S, CALS, AAP, Human Ecology, ILR, Dyson, & Brooks: 1 Core + 3 Concentration + 2 Electives. "
            "Extra Core courses count as Electives; 1 course cannot double-count within the minor (C or higher)."
        ),
    ),
    MinorCollegeDef(
        id="engineering",
        label="Engineering (5 courses)",
        short_label="Engineering (5)",
        total_required_summary="5 courses (1 Core + 3 Conc + 1 Elec)",
        note=(
            "Duffield College of Engineering: 1 Core + 3 Concentration + 1 Elective "
            "(can come from any concentration or Core, incl. INFO 1300). No double-counting within the minor (C or higher)."
        ),
    ),
    MinorCollegeDef(
        id="hotel",
        label="Nolan Hotel School (6 courses)",
        short_label="Nolan Hotel (6)",
        total_required_summary="6 courses (1 Core + 2 Conc + HADM 3740/4760 + 1 Elec)",
        note=(
            "Nolan School of Hotel Administration: 1 Core + 2 Concentration + HADM 3740 + HADM 4760 "
            "+ 1 Elective (INFO 1300 & AEM 3220 count as Electives). No double-counting within the minor (C or higher)."
        ),
    ),
)
_IS_COLLEGES_BY_ID: dict[str, MinorCollegeDef] = {c.id: c for c in INFO_SCIENCE_COLLEGES}


# ---------------------------------------------------------------------------
# 7. Psychology (psychology.cornell.edu/minor & catalog.cornell.edu)
# ---------------------------------------------------------------------------
# Psychology minor requires 18 PSYCH credits (grade C- or higher, letter grade
# except PSYCH 4700/4710 up to 6 cr; no FWS or AP). Area breadth is recommended, not required.


# ---------------------------------------------------------------------------
# Full Registry of 7 Minors
# ---------------------------------------------------------------------------

def _is_concentration_categories(
    conc_id: str,
    conc_label: str,
    conc_short: str,
    conc_courses: frozenset[str],
    tone: str,
) -> tuple[MinorCategoryDef, ...]:
    """Build standard Core + Concentration + Elective category set for an IS concentration."""
    return (
        MinorCategoryDef(
            id="is_core",
            label="IS Core Foundation (1 req)",
            short_label="Core",
            required_summary="1 course",
            rule_summary=(
                "Foundational Info Sci core (INFO 1200, 1260, 1300, 2040, 2450, 2950, or 2951); "
                "additional Core courses also count as Electives (no double-counting)."
            ),
            tone="sky",
            courses=_IS_CORE_ALL,
            required_count=1,
        ),
        MinorCategoryDef(
            id=f"is_conc_{conc_id}",
            label=f"Concentration: {conc_label}",
            short_label=conc_short,
            required_summary="3 courses",
            rule_summary=f"Approved {conc_label} concentration courses (letter grade C or higher at Cornell).",
            tone=tone,
            courses=conc_courses,
            required_count=3,
        ),
        MinorCategoryDef(
            id="is_elective",
            label="IS Electives",
            short_label="Elective",
            required_summary="2 courses",
            rule_summary=(
                "Additional approved concentration courses, extra Core courses (incl. INFO 1200/1260/1300), "
                "or 2000+ INFO courses (no double-counting)."
            ),
            tone="amber",
            courses=_IS_ALL_CONCENTRATION_COURSES | _IS_CORE_ALL,
            dynamic_rule="infosci_elective",
            required_count=2,
        ),
    )


def resolve_is_version_for_college(
    version: MinorVersionDef,
    college_id: str = "",
) -> tuple[MinorVersionDef, str]:
    """Adapt an Info Science MinorVersionDef cleanly to A&S/CALS, Engineering, or Nolan Hotel rules."""
    col = str(college_id or "").strip().lower()
    if col not in _IS_COLLEGES_BY_ID:
        col = "as_cals"

    is_eng = col == "engineering"
    is_hotel = col == "hotel"
    conc_req = 2 if is_hotel else 3
    elec_req = 1 if (is_eng or is_hotel) else 2
    elec_courses = (
        (_IS_ALL_CONCENTRATION_COURSES | _IS_CORE_ALL | _IS_HOTEL_EXTRA_ELECTIVES) - _IS_HOTEL_REQUIRED
        if is_hotel
        else _IS_ALL_CONCENTRATION_COURSES | _IS_CORE_ALL
    )

    adapted: list[MinorCategoryDef] = []
    for cat in version.categories:
        if cat.id == "is_core":
            adapted.append(cat)
            if is_hotel:
                adapted.append(
                    MinorCategoryDef(
                        id="is_hotel_req",
                        label="Nolan Required (HADM 3740 & 4760)",
                        short_label="HADM Req",
                        required_summary="2 required",
                        rule_summary="Both HADM 3740 (Database Mgmt) and HADM 4760 (VBA Programming) are required for Nolan students.",
                        tone="indigo",
                        courses=_IS_HOTEL_REQUIRED,
                        required_count=2,
                    )
                )
        elif cat.id.startswith("is_conc_"):
            adapted.append(
                MinorCategoryDef(
                    id=cat.id,
                    label=cat.label,
                    short_label=cat.short_label,
                    required_summary=f"{conc_req} courses",
                    rule_summary=cat.rule_summary,
                    tone=cat.tone,
                    courses=cat.courses,
                    wildcard_courses=cat.wildcard_courses,
                    dynamic_rule=cat.dynamic_rule,
                    required_count=conc_req,
                )
            )
        elif cat.id == "is_elective":
            elec_rule = (
                "1 additional concentration/Core course, INFO 1300, AEM 3220, or 2000+ INFO (no double-counting)."
                if is_hotel
                else f"{elec_req} additional concentration course{'s' if elec_req > 1 else ''}, extra Core course (incl. INFO 1200/1260/1300), or 2000+ INFO (no double-counting)."
            )
            adapted.append(
                MinorCategoryDef(
                    id="is_elective",
                    label=f"IS Elective{'s' if elec_req > 1 else ''} ({elec_req} req)",
                    short_label="Elective",
                    required_summary=f"{elec_req} course{'s' if elec_req > 1 else ''}",
                    rule_summary=elec_rule,
                    tone=cat.tone,
                    courses=elec_courses,
                    dynamic_rule="infosci_elective_hotel" if is_hotel else "infosci_elective",
                    required_count=elec_req,
                )
            )
        else:
            adapted.append(cat)

    col_def = _IS_COLLEGES_BY_ID[col]
    ds_note = (
        " Important: Cannot pair Data Science concentration with the standalone Data Science Minor."
        if version.id == "data_science"
        else ""
    )
    total_summary = (
        f"{col_def.total_required_summary} (No DS Minor)"
        if version.id == "data_science"
        else col_def.total_required_summary
    )
    return (
        MinorVersionDef(
            id=version.id,
            label=version.label,
            short_label=version.short_label,
            description=f"{col_def.note}{ds_note}",
            total_required_summary=total_summary,
            categories=tuple(adapted),
        ),
        col,
    )


MINORS_REGISTRY: tuple[MinorDef, ...] = (
    MinorDef(
        id="law_society",
        label="Law & Society",
        short_label="Law & Society",
        department="Ethics & Public Life / Philosophy",
        default_version="standard",
        overview="5 approved courses (B- or higher), across >=3 of the 5 categories (max 2 per category, max 2 per dept; all ILR = 1 dept).",
        versions=(
            MinorVersionDef(
                id="standard",
                label="Standard Curriculum (5 Courses)",
                short_label="Standard",
                description=(
                    "Open to all Cornell undergraduates. Requires 5 approved courses (grade B- or better) "
                    "spanning at least 3 of the 5 categories below, with at most 2 courses from any single category "
                    "and at most 2 from any single department (all ILR courses count as 1 department). "
                    "PHIL 2990 may substitute once in any category."
                ),
                total_required_summary="5 courses across >=3 of 5 areas",
                categories=(
                    MinorCategoryDef(
                        id="legal_institutions",
                        label="Category 1: Legal Institutions",
                        short_label="Legal Inst.",
                        required_summary="0-2 courses",
                        rule_summary="Courts, constitutional structure, and legal institutions across U.S. & comparative systems.",
                        tone="sky",
                        courses=_LS_CAT1_LEGAL_INSTITUTIONS,
                        wildcard_courses=_LS_WILDCARD,
                        required_count=2,
                    ),
                    MinorCategoryDef(
                        id="law_policy",
                        label="Category 2: Law & Policy",
                        short_label="Law & Policy",
                        required_summary="0-2 courses",
                        rule_summary="Public policy, regulation, labor/employment law, tech policy, and governance.",
                        tone="emerald",
                        courses=_LS_CAT2_LAW_POLICY,
                        wildcard_courses=_LS_WILDCARD,
                        required_count=2,
                    ),
                    MinorCategoryDef(
                        id="law_social_structure",
                        label="Category 3: Law & Social Structure",
                        short_label="Social Struct.",
                        required_summary="0-2 courses",
                        rule_summary="Race, gender, inequality, sociology of law, and social institutions.",
                        tone="violet",
                        courses=_LS_CAT3_LAW_SOCIAL_STRUCTURE,
                        wildcard_courses=_LS_WILDCARD,
                        required_count=2,
                    ),
                    MinorCategoryDef(
                        id="law_culture",
                        label="Category 4: Law & Culture",
                        short_label="Law & Culture",
                        required_summary="0-2 courses",
                        rule_summary="Cultural, historical, media, and global perspectives on law and justice.",
                        tone="amber",
                        courses=_LS_CAT4_LAW_CULTURE,
                        wildcard_courses=_LS_WILDCARD,
                        required_count=2,
                    ),
                    MinorCategoryDef(
                        id="law_ethics",
                        label="Category 5: Law & Ethics",
                        short_label="Law & Ethics",
                        required_summary="0-2 courses",
                        rule_summary="Moral philosophy, bioethics, human rights, and computing/AI ethics.",
                        tone="rose",
                        courses=_LS_CAT5_LAW_ETHICS,
                        wildcard_courses=_LS_WILDCARD,
                        required_count=2,
                    ),
                ),
            ),
        ),
    ),
    MinorDef(
        id="business",
        label="Business",
        short_label="Business",
        department="SC Johnson College of Business",
        default_version="general",
        overview="Core business foundation in microeconomics, management, marketing, financial accounting, finance, and capstone.",
        versions=(
            MinorVersionDef(
                id="general",
                label="General Business Minor (Current 16.5 cr)",
                short_label="General (16.5 cr)",
                description=(
                    "For all non-Dyson/Nolan Cornell undergrads whose major doesn't overlap >=2 core business courses. "
                    "Requires Microeconomics (3 cr) + Management (3 cr) + Marketing (3 cr) + Accounting (3 cr) + Finance (3 cr) "
                    "+ Capstone Elective (1.5 cr). At least 7.5 cr must be SC Johnson (AEM/HADM/NBA/NCC); letter grade C+."
                ),
                total_required_summary="16.5 credits (6 requirements)",
                categories=(
                    MinorCategoryDef(
                        id="microeconomics",
                        label="Foundation: Microeconomics (3 cr)",
                        short_label="Microecon",
                        required_summary="1 course (3 cr)",
                        rule_summary="ECON 1110, ECON 3030, or PUBPOL 2000 (letter grade C or higher).",
                        tone="sky",
                        courses=_BUS_MICRO,
                    ),
                    MinorCategoryDef(
                        id="management",
                        label="Intro to Management (3 cr)",
                        short_label="Management",
                        required_summary="1 course (3 cr)",
                        rule_summary="AEM 1200, HADM 1810 (Spring only), ILRID 1700 (non-ILR), or NCC 5540.",
                        tone="emerald",
                        courses=_BUS_MGMT,
                    ),
                    MinorCategoryDef(
                        id="marketing",
                        label="Intro to Marketing (3 cr)",
                        short_label="Marketing",
                        required_summary="1 course (3 cr)",
                        rule_summary="AEM 2400 or HADM 2410 (Fall only).",
                        tone="violet",
                        courses=_BUS_MKTG,
                    ),
                    MinorCategoryDef(
                        id="accounting",
                        label="Financial Accounting (3 cr)",
                        short_label="Accounting",
                        required_summary="1 course (3 cr)",
                        rule_summary="AEM 2210, HADM 2230, or NCC 5500.",
                        tone="amber",
                        courses=_BUS_ACCT,
                    ),
                    MinorCategoryDef(
                        id="finance",
                        label="Finance (3 cr)",
                        short_label="Finance",
                        required_summary="1 course (3 cr)",
                        rule_summary="AEM 2241, HADM 2250, or NCC 5560.",
                        tone="teal",
                        courses=_BUS_FIN,
                    ),
                    MinorCategoryDef(
                        id="capstone_elective",
                        label="Capstone Elective (1.5 cr)",
                        short_label="Capstone",
                        required_summary="1 course (1.5 cr)",
                        rule_summary="Required under current curriculum (AEM 4940-001 Business Simulation / AEM 4660 / AEM 4665).",
                        tone="rose",
                        courses=_BUS_GENERAL_CAPSTONE,
                    ),
                ),
            ),
            MinorVersionDef(
                id="general_pre",
                label="General Business (Previous 15 cr Curriculum)",
                short_label="General (Prev 15 cr)",
                description=(
                    "For students admitted under the previous General Business Minor curriculum (no 1.5 cr capstone elective required). "
                    "Requires Microeconomics + Management + Marketing + Financial Accounting + Finance."
                ),
                total_required_summary="15 credits (5 requirements)",
                categories=(
                    MinorCategoryDef(
                        id="microeconomics",
                        label="Foundation: Microeconomics (3 cr)",
                        short_label="Microecon",
                        required_summary="1 course (3 cr)",
                        rule_summary="ECON 1110, ECON 3030, or PUBPOL 2000.",
                        tone="sky",
                        courses=_BUS_MICRO,
                    ),
                    MinorCategoryDef(
                        id="management",
                        label="Intro to Management (3 cr)",
                        short_label="Management",
                        required_summary="1 course (3 cr)",
                        rule_summary="AEM 1200, HADM 1810, ILRID 1700, or NCC 5540.",
                        tone="emerald",
                        courses=_BUS_MGMT,
                    ),
                    MinorCategoryDef(
                        id="marketing",
                        label="Intro to Marketing (3 cr)",
                        short_label="Marketing",
                        required_summary="1 course (3 cr)",
                        rule_summary="AEM 2400 or HADM 2410.",
                        tone="violet",
                        courses=_BUS_MKTG,
                    ),
                    MinorCategoryDef(
                        id="accounting",
                        label="Financial Accounting (3 cr)",
                        short_label="Accounting",
                        required_summary="1 course (3 cr)",
                        rule_summary="AEM 2210, HADM 2230, or NCC 5500.",
                        tone="amber",
                        courses=_BUS_ACCT,
                    ),
                    MinorCategoryDef(
                        id="finance",
                        label="Finance (3 cr)",
                        short_label="Finance",
                        required_summary="1 course (3 cr)",
                        rule_summary="AEM 2241, HADM 2250, or NCC 5560.",
                        tone="teal",
                        courses=_BUS_FIN,
                    ),
                ),
            ),
            MinorVersionDef(
                id="bme",
                label="Business Minor for Engineers (BME)",
                short_label="BME (Engineers/CS)",
                description=(
                    "For Duffield Engineering majors, A&S/CALS Computer Science or Information Science majors, and CALS Bio/Env Engineering. "
                    "Requires Microecon (3 cr) + Intro Business (3 cr, Mgmt OR Mktg) + Accounting (3 cr, ORIE 3150 ok for ORIE) "
                    "+ Finance (3 cr) + AEM 4660 Business Simulation (1.5 cr) + 3 cr upper-level SC Johnson (3000+ AEM/HADM/NBA/NCC) Career Goals."
                ),
                total_required_summary="16.5 credits (6 requirements)",
                categories=(
                    MinorCategoryDef(
                        id="microeconomics",
                        label="Foundation: Microeconomics (3 cr)",
                        short_label="Microecon",
                        required_summary="1 course (3 cr)",
                        rule_summary="ECON 1110, ECON 3030, or PUBPOL 2000.",
                        tone="sky",
                        courses=_BUS_MICRO,
                    ),
                    MinorCategoryDef(
                        id="intro_business",
                        label="Intro Business Concepts (Mgmt or Mktg, 3 cr)",
                        short_label="Intro Bus.",
                        required_summary="1 course (3 cr)",
                        rule_summary="AEM 1200, HADM 1810, AEM 2400, HADM 2410, ILRID 1700, or NCC 5530/5540.",
                        tone="emerald",
                        courses=_BUS_BME_INTRO,
                    ),
                    MinorCategoryDef(
                        id="accounting_bme",
                        label="Accounting Principles (3 cr)",
                        short_label="Accounting",
                        required_summary="1 course (3 cr)",
                        rule_summary="AEM 2210, HADM 2230, NCC 5500, or ORIE 3150 (ORIE majors only).",
                        tone="amber",
                        courses=_BUS_ACCT_BME,
                    ),
                    MinorCategoryDef(
                        id="finance",
                        label="Finance (3 cr)",
                        short_label="Finance",
                        required_summary="1 course (3 cr)",
                        rule_summary="AEM 2241, HADM 2250, or NCC 5560.",
                        tone="teal",
                        courses=_BUS_FIN,
                    ),
                    MinorCategoryDef(
                        id="bme_capstone",
                        label="Capstone: AEM 4660 Business Simulation (1.5 cr)",
                        short_label="AEM 4660",
                        required_summary="1 course (1.5 cr)",
                        rule_summary="AEM 4660 Business Simulation required.",
                        tone="rose",
                        courses=_BUS_BME_CAPSTONE,
                    ),
                    MinorCategoryDef(
                        id="bme_career_goals",
                        label="Career Goals: 3000+ SC Johnson Course (3 cr)",
                        short_label="3000+ Bus.",
                        required_summary="3 credits",
                        rule_summary="Any 3000+ letter-grade SC Johnson (AEM/HADM/NBA/NCC) course (excluding IND/RSC/capstone/AEM 3100 for ORIE).",
                        tone="violet",
                        dynamic_rule="bme_career_goals",
                        required_credits=3.0,
                    ),
                ),
            ),
            MinorVersionDef(
                id="dbmls",
                label="Dyson Business Minor for Life Sciences (DBMLS)",
                short_label="DBMLS (Life Sci)",
                description=(
                    "For Life Sciences and pre-health majors in CALS, A&S, Human Ecology, Brooks Health Care Policy, or BioEng. "
                    "Requires Microecon (3 cr) + Mgmt/Marketing (3 cr) + Accounting (3 cr) + Finance (3 cr) "
                    "+ Approved Life Sciences/Business Career Goals (3 cr) + Capstone AEM 4661 (1.5 cr)."
                ),
                total_required_summary="16.5 credits (6 requirements)",
                categories=(
                    MinorCategoryDef(
                        id="microeconomics",
                        label="Foundation: Microeconomics (3 cr)",
                        short_label="Microecon",
                        required_summary="1 course (3 cr)",
                        rule_summary="ECON 1110, ECON 3030, or PUBPOL 2000.",
                        tone="sky",
                        courses=_BUS_MICRO,
                    ),
                    MinorCategoryDef(
                        id="mgmt_or_mktg",
                        label="Management or Marketing (3 cr)",
                        short_label="Mgmt/Mktg",
                        required_summary="1 course (3 cr)",
                        rule_summary="AEM 1200, HADM 1810, AEM 2400, HADM 2410, ILRID 1700, or NCC 5540.",
                        tone="emerald",
                        courses=_BUS_DBMLS_MGMT_MKTG,
                    ),
                    MinorCategoryDef(
                        id="accounting",
                        label="Financial Accounting (3 cr)",
                        short_label="Accounting",
                        required_summary="1 course (3 cr)",
                        rule_summary="AEM 2210, HADM 2230, or NCC 5500.",
                        tone="amber",
                        courses=_BUS_ACCT,
                    ),
                    MinorCategoryDef(
                        id="finance",
                        label="Finance (3 cr)",
                        short_label="Finance",
                        required_summary="1 course (3 cr)",
                        rule_summary="AEM 2241, HADM 2250, or NCC 5560.",
                        tone="teal",
                        courses=_BUS_FIN,
                    ),
                    MinorCategoryDef(
                        id="dbmls_career_goals",
                        label="Career Goals Electives (3 cr)",
                        short_label="Career Goals",
                        required_summary="3 credits",
                        rule_summary="Approved Entrepreneurship, Life Sci/Healthcare Business, Mgmt/Fin, or Spreadsheet/Strategy courses.",
                        tone="violet",
                        courses=_BUS_DBMLS_CAREER,
                        required_credits=3.0,
                    ),
                    MinorCategoryDef(
                        id="dbmls_capstone",
                        label="Capstone: AEM 4661 Life Sci Simulation (1.5 cr)",
                        short_label="AEM 4661",
                        required_summary="1 course (1.5 cr)",
                        rule_summary="AEM 4661 Business Simulation Capstone for Business Minors in Life Sciences.",
                        tone="rose",
                        courses=_BUS_DBMLS_CAPSTONE,
                    ),
                ),
            ),
        ),
    ),
    MinorDef(
        id="inequality",
        label="Inequality Studies",
        short_label="Inequality Studies",
        department="Center for the Study of Inequality",
        default_version="general",
        overview="6 courses (>=18 cr): Core (SOC 2208) + 1 Overview + 4 Electives across >=3 departments (at least 2 @ 3000+ level).",
        versions=(
            MinorVersionDef(
                id="general",
                label="General Track (6 Courses)",
                short_label="General",
                description=(
                    "For all Cornell undergraduates pursuing Inequality Studies without a specialized track. "
                    "Requires SOC/AMST/PUBPOL 2208 + 1 Overview course + 4 approved Electives (>=3 departments total, >=2 courses at 3000+)."
                ),
                total_required_summary="6 courses (>=18 cr)",
                categories=(
                    MinorCategoryDef(
                        id="ineq_core",
                        label="Core Course: Social Inequality",
                        short_label="Core (2208)",
                        required_summary="1 course",
                        rule_summary="SOC 2208 / AMST 2208 / PUBPOL 2208.",
                        tone="sky",
                        courses=_INEQ_CORE,
                    ),
                    MinorCategoryDef(
                        id="ineq_overview",
                        label="Overview Course (1 required)",
                        short_label="Overview",
                        required_summary="1 course",
                        rule_summary="Broad survey (SOC 2220, PUBPOL 2250, SOC 2370, GDEV 3700 / SOC 3710, etc.). Extra Overview also counts as an Elective.",
                        tone="emerald",
                        courses=_INEQ_OVERVIEW,
                    ),
                    MinorCategoryDef(
                        id="ineq_elective",
                        label="Inequality Electives (4 required)",
                        short_label="Elective",
                        required_summary="4 courses",
                        rule_summary="Approved FA26/SP27 Inequality electives across departments (>=2 at 3000+ level, >=3 depts total).",
                        tone="violet",
                        courses=_INEQ_ALL_ELECTIVES,
                        required_count=4,
                    ),
                ),
            ),
            MinorVersionDef(
                id="health_equity",
                label="Health Equity Track (HET)",
                short_label="Health Equity (HET)",
                description=(
                    "Optional specialization exploring social determinants of health & healthcare disparities. "
                    "Requires SOC 2208 + 1 Overview + at least 2 HET-designated Electives + 2 additional Electives."
                ),
                total_required_summary="6 courses (>=2 HET electives)",
                categories=(
                    MinorCategoryDef(
                        id="ineq_core",
                        label="Core Course: Social Inequality",
                        short_label="Core (2208)",
                        required_summary="1 course",
                        rule_summary="SOC 2208 / AMST 2208 / PUBPOL 2208.",
                        tone="sky",
                        courses=_INEQ_CORE,
                        required_count=1,
                    ),
                    MinorCategoryDef(
                        id="ineq_overview",
                        label="Overview Course (1 required)",
                        short_label="Overview",
                        required_summary="1 course",
                        rule_summary="Broad survey course (extra Overview counts as an Elective).",
                        tone="emerald",
                        courses=_INEQ_OVERVIEW,
                        required_count=1,
                    ),
                    MinorCategoryDef(
                        id="ineq_het_elective",
                        label="Health Equity Track (HET) Electives (>=2)",
                        short_label="HET Elective",
                        required_summary="2+ courses",
                        rule_summary="Courses with official Center for the Study of Inequality HET designation.",
                        tone="rose",
                        courses=_INEQ_HET_ELECTIVES,
                        required_count=2,
                    ),
                    MinorCategoryDef(
                        id="ineq_elective",
                        label="Other Inequality Electives (2 req)",
                        short_label="Elective",
                        required_summary="2 courses",
                        rule_summary="Any approved non-HET or additional HET Inequality elective.",
                        tone="violet",
                        courses=_INEQ_REG_ELECTIVES,
                        required_count=2,
                    ),
                ),
            ),
        ),
    ),
    MinorDef(
        id="lsj",
        label="Labor & Social Justice",
        short_label="Labor & Social Justice",
        department="ILR Global Labor & Work",
        default_version="standard",
        overview="15 letter-grade credits with the ILRGL prefix (excluding internships, independent/directed studies, and honors theses).",
        versions=(
            MinorVersionDef(
                id="standard",
                label="Standard (15 Credits ILRGL)",
                short_label="Standard",
                description=(
                    "Open to all Cornell undergraduates (including ILR students; max 3 cr double-counted with major/other minors). "
                    "Requires 15 letter-grade ILRGL credits; 1-cr ILR internships, honors theses, directed study, and independent study cannot count."
                ),
                total_required_summary="15 credits (ILRGL letter-grade)",
                categories=(
                    MinorCategoryDef(
                        id="lsj_ilrgl",
                        label="ILRGL Letter-Grade Courses (15 cr)",
                        short_label="ILRGL Minor",
                        required_summary="15 credits",
                        rule_summary="Any ILRGL (or ILRGL-crosslisted) undergraduate course taken for a letter grade, excluding independent study/internships/honors.",
                        tone="teal",
                        dynamic_rule="lsj_ilrgl",
                        required_credits=15.0,
                    ),
                ),
            ),
        ),
    ),
    MinorDef(
        id="history",
        label="History",
        short_label="History",
        department="Department of History",
        default_version="standard",
        overview="5 HIST courses (3-4 cr, letter grade C+), excluding FWS/independent study/honors, including at least one 2000+ Seminar.",
        versions=(
            MinorVersionDef(
                id="standard",
                label="Standard (5 HIST Courses)",
                short_label="Standard",
                description=(
                    "Open to Cornell undergraduates (check home college rules). Requires 5 HIST (or HIST-crosslisted) courses "
                    "of 3-4+ credits taken for a letter grade (C+ or better). Excludes FWS, independent study, and honors; "
                    "must include at least one 2000+ level seminar."
                ),
                total_required_summary="5 courses (incl. >=1 2000+ Seminar)",
                categories=(
                    MinorCategoryDef(
                        id="hist_seminar_2000",
                        label="2000+ History Seminar (>=1 required)",
                        short_label="2000+ Sem",
                        required_summary=">=1 course",
                        rule_summary="Any 2000-4999 HIST seminar (SEM component, >=3 cr, letter grade; excludes FWS, independent study & honors).",
                        tone="amber",
                        dynamic_rule="history_seminar_2000",
                        required_count=1,
                    ),
                    MinorCategoryDef(
                        id="hist_course",
                        label="HIST Courses (Non-FWS, 3-4 cr)",
                        short_label="HIST Course",
                        required_summary="4+ courses",
                        rule_summary="Any 1000-4999 HIST lecture or seminar >=3 cr for letter grade (excludes FWS, HIST 2001/3002/4001/4002/8004).",
                        tone="sky",
                        dynamic_rule="history_non_fws",
                        required_count=4,
                    ),
                ),
            ),
        ),
    ),
    MinorDef(
        id="info_science",
        label="Information Science",
        short_label="Info Science",
        department="Bowers CIS — Information Science",
        default_version="all",
        default_college="as_cals",
        colleges=INFO_SCIENCE_COLLEGES,
        overview="5-6 Cornell letter-grade courses (C or higher), tailored by college: A&S/CALS (6), Engineering (5), or Nolan Hotel (6). Extra Core courses count as Electives; no double-counting inside the minor.",
        versions=(
            MinorVersionDef(
                id="all",
                label="All Concentrations (Compare Tracks)",
                short_label="All Tracks",
                description=(
                    "Shows Info Sci Core, all 7 concentrations, and Electives. Requirements adapt to your college; "
                    "no course may count more than once within the minor."
                ),
                total_required_summary="6 courses (1 Core + 3 Conc + 2 Elec)",
                categories=(
                    MinorCategoryDef(
                        id="is_core",
                        label="IS Core Foundation (1 req)",
                        short_label="IS Core",
                        required_summary="1 course",
                        rule_summary="INFO 1200, 1260, 1300, 2040, 2450, 2950, or 2951 (extra Core courses count as Electives).",
                        tone="sky",
                        courses=_IS_CORE_ALL,
                        required_count=1,
                    ),
                    MinorCategoryDef(
                        id="is_conc_behavioral_science",
                        label="Conc: Behavioral Science",
                        short_label="Behavioral Sci",
                        required_summary="3 courses",
                        rule_summary="Human interaction, social computing, & behavioral analytics.",
                        tone="emerald",
                        courses=_IS_BEHAVIORAL,
                        required_count=3,
                    ),
                    MinorCategoryDef(
                        id="is_conc_data_science",
                        label="Conc: Data Science",
                        short_label="Data Science",
                        required_summary="3 courses",
                        rule_summary="Data analytics, visualization, & ML (cannot double with Data Science Minor).",
                        tone="violet",
                        courses=_IS_DATA_SCIENCE,
                        required_count=3,
                    ),
                    MinorCategoryDef(
                        id="is_conc_digital_culture",
                        label="Conc: Digital Culture & Production",
                        short_label="Digital Culture",
                        required_summary="3 courses",
                        rule_summary="Cultural analytics, media history, & digital creation.",
                        tone="amber",
                        courses=_IS_DIGITAL_CULTURE,
                        required_count=3,
                    ),
                    MinorCategoryDef(
                        id="is_conc_ethics_law_policy",
                        label="Conc: Info Ethics, Law & Policy",
                        short_label="Ethics/Policy",
                        required_summary="3 courses",
                        rule_summary="Privacy, AI governance, IP law, fairness, & tech policy.",
                        tone="rose",
                        courses=_IS_ETHICS_LAW,
                        required_count=3,
                    ),
                    MinorCategoryDef(
                        id="is_conc_interactive_tech",
                        label="Conc: Interactive Technologies",
                        short_label="Interactive Tech",
                        required_summary="3 courses",
                        rule_summary="Web systems, prototyping, games, HCI engineering & physical computing.",
                        tone="teal",
                        courses=_IS_INTERACTIVE_TECH,
                        required_count=3,
                    ),
                    MinorCategoryDef(
                        id="is_conc_networks_crowds_markets",
                        label="Conc: Networks, Crowds & Markets",
                        short_label="Networks/Mkts",
                        required_summary="3 courses",
                        rule_summary="Network modeling, game theory, market design, & empirical analysis.",
                        tone="indigo",
                        courses=_IS_NETWORKS_MARKETS,
                        required_count=3,
                    ),
                    MinorCategoryDef(
                        id="is_conc_ux",
                        label="Conc: User Experience (UX)",
                        short_label="UX Design",
                        required_summary="3 courses",
                        rule_summary="Human-centered design, user research, & HCI studio prototyping.",
                        tone="emerald",
                        courses=_IS_UX,
                        required_count=3,
                    ),
                    MinorCategoryDef(
                        id="is_elective",
                        label="IS Electives",
                        short_label="Elective",
                        required_summary="2 courses",
                        rule_summary="Additional approved concentration courses, extra Core courses, or 2000+ INFO (no double-counting).",
                        tone="amber",
                        courses=_IS_ALL_CONCENTRATION_COURSES | _IS_CORE_ALL,
                        dynamic_rule="infosci_elective",
                        required_count=2,
                    ),
                ),
            ),
            MinorVersionDef(
                id="behavioral_science",
                label="Track: Behavioral Science",
                short_label="Behavioral Sci",
                description=(
                    "For students focusing on psychology, social behavior, and human-AI interaction. "
                    "Complete 1 Core + 3 Behavioral Science courses + 1 Elective (Engineering) or 2 Electives (A&S/CALS). Grade C or higher."
                ),
                total_required_summary="5-6 courses",
                categories=_is_concentration_categories(
                    "behavioral_science", "Behavioral Science", "Behavioral Sci", _IS_BEHAVIORAL, "emerald"
                ),
            ),
            MinorVersionDef(
                id="data_science",
                label="Track: Data Science",
                short_label="Data Science",
                description=(
                    "For students focusing on data analytics, machine learning, and visualization. "
                    "Important: Students completing the IS Minor Data Science concentration CANNOT also declare Cornell's Data Science Minor."
                ),
                total_required_summary="5-6 courses (No DS Minor)",
                categories=_is_concentration_categories(
                    "data_science", "Data Science", "Data Science", _IS_DATA_SCIENCE, "violet"
                ),
            ),
            MinorVersionDef(
                id="digital_culture",
                label="Track: Digital Culture & Production",
                short_label="Digital Culture",
                description=(
                    "For students bridging humanities, digital media, cultural analytics, and computing history. "
                    "1 Core + 3 Digital Culture courses + 1-2 Electives (Eng vs A&S/CALS)."
                ),
                total_required_summary="5-6 courses",
                categories=_is_concentration_categories(
                    "digital_culture", "Digital Culture & Production", "Digital Culture", _IS_DIGITAL_CULTURE, "amber"
                ),
            ),
            MinorVersionDef(
                id="ethics_law_policy",
                label="Track: Information Ethics, Law & Policy",
                short_label="Ethics/Policy",
                description=(
                    "For students interested in AI governance, privacy, copyright, algorithmic fairness, and tech regulation. "
                    "1 Core + 3 Ethics/Law/Policy courses + 1-2 Electives (Eng vs A&S/CALS)."
                ),
                total_required_summary="5-6 courses",
                categories=_is_concentration_categories(
                    "ethics_law_policy", "Info Ethics, Law & Policy", "Ethics/Policy", _IS_ETHICS_LAW, "rose"
                ),
            ),
            MinorVersionDef(
                id="interactive_tech",
                label="Track: Interactive Technologies",
                short_label="Interactive Tech",
                description=(
                    "For students focused on hands-on interactive software/hardware engineering, web apps, games, and physical computing. "
                    "1 Core + 3 Interactive Tech courses + 1-2 Electives (Eng vs A&S/CALS)."
                ),
                total_required_summary="5-6 courses",
                categories=_is_concentration_categories(
                    "interactive_tech", "Interactive Technologies", "Interactive Tech", _IS_INTERACTIVE_TECH, "teal"
                ),
            ),
            MinorVersionDef(
                id="networks_crowds_markets",
                label="Track: Networks, Crowds & Markets",
                short_label="Networks/Mkts",
                description=(
                    "For students studying network science, game theory, market design, and socio-economic platforms. "
                    "1 Core + 3 Networks/Crowds/Markets courses + 1-2 Electives (Eng vs A&S/CALS)."
                ),
                total_required_summary="5-6 courses",
                categories=_is_concentration_categories(
                    "networks_crowds_markets", "Networks, Crowds & Markets", "Networks/Mkts", _IS_NETWORKS_MARKETS, "indigo"
                ),
            ),
            MinorVersionDef(
                id="ux",
                label="Track: User Experience (UX)",
                short_label="UX Design",
                description=(
                    "For students focusing on HCI design, user research, prototyping, and Human-AI interface design. "
                    "1 Core + 3 UX courses + 1-2 Electives (Eng vs A&S/CALS)."
                ),
                total_required_summary="5-6 courses",
                categories=_is_concentration_categories(
                    "ux", "User Experience (UX)", "UX Design", _IS_UX, "emerald"
                ),
            ),
        ),
    ),
    MinorDef(
        id="psychology",
        label="Psychology",
        short_label="Psychology",
        department="Department of Psychology",
        default_version="standard",
        overview="18 credits in PSYCH (C- or better, letter grade except PSYCH 4700/4710 up to 6 cr; no FWS or AP). Area breadth is recommended, not required.",
        versions=(
            MinorVersionDef(
                id="standard",
                label="Standard (18 Credits)",
                short_label="Standard",
                description=(
                    "Open to all Cornell undergrads outside Psychology/HD. Requires 18 credits in PSYCH (grade C- or higher; "
                    "letter-grade except PSYCH 4700/4710 research up to 6 cr; no FWS or AP credits). "
                    "Taking courses across different subfields is recommended, not required."
                ),
                total_required_summary="18 credits (non-FWS PSYCH)",
                categories=(
                    MinorCategoryDef(
                        id="psych_course",
                        label="PSYCH Courses (18 credits)",
                        short_label="PSYCH Course",
                        required_summary="18 credits",
                        rule_summary="Any non-FWS undergraduate PSYCH course (1000-4999, C- or better letter grade; AP & FWS excluded; up to 6 cr PSYCH 4700/4710).",
                        tone="sky",
                        dynamic_rule="psych_course",
                        required_credits=18.0,
                    ),
                ),
            ),
        ),
    ),
)

MINORS_BY_ID: dict[str, MinorDef] = {m.id: m for m in MINORS_REGISTRY}
