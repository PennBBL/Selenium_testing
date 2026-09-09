from dataclasses import dataclass


@dataclass(frozen=True)
class ResultsConfig:
    test_name: str
    csv_file: str
    target_scores: list[str]


RESULTS_CONFIGS = {
    # ------------------------------------------------------------------
    # ER40
    # ------------------------------------------------------------------
    "k-er40-d-4.60-ff": ResultsConfig(
        test_name="k-er40-d-4.60-ff",
        csv_file="er40_results.csv",
        target_scores=[
            "ScorVers",
            "ER40D_CR",
            "ER40D_RTCR",
            "ER40D_LRSR",
        ],
    ),

    # ------------------------------------------------------------------
    # CPW
    # ------------------------------------------------------------------
    "k-cpw-3.01-ff": ResultsConfig(
        test_name="k-cpw-3.01-ff",
        csv_file="cpw_results.csv",
        target_scores=[
            "ScorVers",
            "CPW_CR",
            "CPW_PC",
            "CPW_RTCR",
            "CPW_TP",
        ],
    ),

    # ------------------------------------------------------------------
    # VSPLOT
    # ------------------------------------------------------------------
    "zn_CN-vsplot24-2.10-ff": ResultsConfig(
        test_name="zn_CN-vsplot24-2.10-ff",
        csv_file="vsplot_results.csv",
        target_scores=[
            "ScorVers",
            "VSPLOT24_CR",
            "VSPLOT24_PC",
            "VSPLOT24_RTCR",
            "VSPLOT24_ER",
            "VSPLOT24_RTER",
            "VSPLOT24_RT",
        ],
    ),

    # ------------------------------------------------------------------
    # MEDF
    # ------------------------------------------------------------------
    "medf36-a-3.06-ff": ResultsConfig(
        test_name="medf36-a-3.06-ff",
        csv_file="medf_results.csv",
        target_scores=[
            "ScorVers",
            "MEDF36A_CR",
            "MEDF36A_PC",
            "MEDF36A_RTCR",
            "MEDF36A_ER",
        ],
    ),

    # ------------------------------------------------------------------
    # ADT
    # ------------------------------------------------------------------
    "adt36-a-3.07-ff": ResultsConfig(
        test_name="adt36-a-3.07-ff",
        csv_file="adt_results.csv",
        target_scores=[
            "ScorVers",
            "ADT36A_CR",
            "ADT36A_PC",
            "ADT36A_RTCR",
            "ADT36A_ER",
        ],
    ),

    "adt36-b-2.07-ff": ResultsConfig(
        test_name="adt36-b-2.07-ff",
        csv_file="adt_results.csv",
        target_scores=[
            "ScorVers",
            "ADT36B_CR",
            "ADT36B_PC",
            "ADT36B_RTCR",
            "ADT36B_ER",
        ],
    ),

    # ------------------------------------------------------------------
    # Motor Praxis
    # ------------------------------------------------------------------
    "mpraxis-2.06-ff": ResultsConfig(
        test_name="mpraxis-2.06-ff",
        csv_file="mpraxis_results.csv",
        target_scores=[
            "ScorVers",
            "MP1RT",
            "MP2",
            "MP2RTCR",
            "MP_EFF",
        ],
    ),

    # ------------------------------------------------------------------
    # SVOLT delayed
    # ------------------------------------------------------------------
    "svoltd-3.00-ff": ResultsConfig(
        test_name="svoltd-3.00-ff",
        csv_file="svoltd_results.csv",
        target_scores=[
            "ScorVers",
            "SVOLT_CR",
            "SVOLT_RTCR",
            "SVOLT_ER",
            "SVOLT_RTER",
            # Add confirmed SVOLTD score names after raw scrape.
        ],
    ),

    # ------------------------------------------------------------------
    # SVOLT regular / short version
    # ------------------------------------------------------------------
    "zn_CN-k-svolt-3.01-ff": ResultsConfig(
        test_name="zn_CN-k-svolt-3.01-ff",
        csv_file="svolt_results.csv",
        target_scores=[
            "ScorVers",
            "SVOLT_CR",
            "SVOLT_RTCR",
            "SVOLT_ER",
            "SVOLT_RTER",
            
        ],
    ),

    # ------------------------------------------------------------------
    # CPF
    # ------------------------------------------------------------------
    "cpf-2.05-ff": ResultsConfig(
        test_name="cpf-2.05-ff",
        csv_file="cpf_results.csv",
        target_scores=[
            "ScorVers",
            "CPF_CR",
            "CPF_RTCR",
            "CPF_ER",
            # Add confirmed CPF score names after raw scrape.
        ],
    ),

    # ------------------------------------------------------------------
    # CPFD
    # ------------------------------------------------------------------
    "cpfd-2.05-ff": ResultsConfig(
        test_name="cpfd-2.05-ff",
        csv_file="cpfd_results.csv",
        target_scores=[
            "ScorVers",
            # Add confirmed CPFD score names after raw scrape.
        ],
    ),

    # ------------------------------------------------------------------
    # PMAT
    # ------------------------------------------------------------------
    "pmat24-a-2.00-ff": ResultsConfig(
        test_name="pmat24-a-2.00-ff",
        csv_file="pmat_results.csv",
        target_scores=[
            "ScorVers",
            # Add confirmed PMAT score names after raw scrape.
        ],
    ),

    # ------------------------------------------------------------------
    # PCET
    # ------------------------------------------------------------------
    "k-pcet-3.00-ff": ResultsConfig(
        test_name="k-pcet-3.00-ff",
        csv_file="pcet_results.csv",
        target_scores=[
            "ScorVers",
            "PCET_CR",
            "PCET_RTCR",
            "PCET_ER",
            "PCET_RTER",
            # Add confirmed PCET score names after raw scrape.
        ],
    ),

    # ------------------------------------------------------------------
    # SPCPTNL
    # ------------------------------------------------------------------
    "spcptnl-2.01-ff": ResultsConfig(
        test_name="spcptnl-2.01-ff",
        csv_file="spcptnl_results.csv",
        target_scores=[
            "ScorVers",
            # Add confirmed SPCPTNL score names after raw scrape.
        ],
    ),
}


def _add_alias(alias_code: str, base_code: str):
    """
    Add a RESULTS_CONFIGS alias while preserving the actual test code
    that appeared in the battery result.

    This avoids KeyError in the scraper and keeps the CSV test_name accurate.
    """
    base = RESULTS_CONFIGS[base_code]

    RESULTS_CONFIGS[alias_code] = ResultsConfig(
        test_name=alias_code,
        csv_file=base.csv_file,
        target_scores=base.target_scores,
    )


# ----------------------------------------------------------------------
# ER40 aliases
# ----------------------------------------------------------------------
# Add here if language-prefixed ER40 codes appear later.


# ----------------------------------------------------------------------
# CPW aliases
# ----------------------------------------------------------------------
_add_alias("zn_CN-k-cpw-3.01-ff", "k-cpw-3.01-ff")
_add_alias("zh_CN-k-cpw-3.01-ff", "k-cpw-3.01-ff")

# Older Chinese CPW version seen in battery logs.
_add_alias("zn_CN-k-cpw-1.00-ff", "k-cpw-3.01-ff")
_add_alias("zh_CN-k-cpw-1.00-ff", "k-cpw-3.01-ff")


# ----------------------------------------------------------------------
# VSPLOT aliases
# ----------------------------------------------------------------------
_add_alias("vsplot24-2.10-ff", "zn_CN-vsplot24-2.10-ff")
_add_alias("zh_CN-vsplot24-2.10-ff", "zn_CN-vsplot24-2.10-ff")
_add_alias("kr_KR-vsplot24-2.10-ff", "zn_CN-vsplot24-2.10-ff")


# ----------------------------------------------------------------------
# MEDF aliases
# ----------------------------------------------------------------------
_add_alias("zn_CN-medf36-a-3.06-ff", "medf36-a-3.06-ff")
_add_alias("zh_CN-medf36-a-3.06-ff", "medf36-a-3.06-ff")
_add_alias("kr_KR-medf36-a-3.06-ff", "medf36-a-3.06-ff")


# ----------------------------------------------------------------------
# ADT aliases
# ----------------------------------------------------------------------
_add_alias("zn_CN-adt36-a-3.07-ff", "adt36-a-3.07-ff")
_add_alias("zh_CN-adt36-a-3.07-ff", "adt36-a-3.07-ff")
_add_alias("kr_KR-adt36-a-3.07-ff", "adt36-a-3.07-ff")

_add_alias("zn_CN-adt36-b-2.07-ff", "adt36-b-2.07-ff")
_add_alias("zh_CN-adt36-b-2.07-ff", "adt36-b-2.07-ff")
_add_alias("kr_KR-adt36-b-2.07-ff", "adt36-b-2.07-ff")


# ----------------------------------------------------------------------
# Motor Praxis aliases
# ----------------------------------------------------------------------
_add_alias("zn_CN-mpraxis-2.06-ff", "mpraxis-2.06-ff")
_add_alias("zh_CN-mpraxis-2.06-ff", "mpraxis-2.06-ff")
_add_alias("kr_KR-mpraxis-2.06-ff", "mpraxis-2.06-ff")

# k-prefixed Motor Praxis codes seen in battery logs.
_add_alias("zn_CN-k-mpraxis-2.06-ff", "mpraxis-2.06-ff")
_add_alias("zh_CN-k-mpraxis-2.06-ff", "mpraxis-2.06-ff")
_add_alias("kr_KR-k-mpraxis-2.06-ff", "mpraxis-2.06-ff")
_add_alias("k-mpraxis-2.06-ff", "mpraxis-2.06-ff")


# ----------------------------------------------------------------------
# SVOLTD aliases
# ----------------------------------------------------------------------
_add_alias("zn_CN-svoltd-3.00-ff", "svoltd-3.00-ff")
_add_alias("zh_CN-svoltd-3.00-ff", "svoltd-3.00-ff")
_add_alias("kr_KR-svoltd-3.00-ff", "svoltd-3.00-ff")


# ----------------------------------------------------------------------
# SVOLT regular aliases
# ----------------------------------------------------------------------
_add_alias("zh_CN-k-svolt-3.01-ff", "zn_CN-k-svolt-3.01-ff")
_add_alias("kr_KR-k-svolt-3.01-ff", "zn_CN-k-svolt-3.01-ff")
_add_alias("k-svolt-3.01-ff", "zn_CN-k-svolt-3.01-ff")


# ----------------------------------------------------------------------
# CPF aliases
# ----------------------------------------------------------------------
_add_alias("zn_CN-cpf-2.05-ff", "cpf-2.05-ff")
_add_alias("zh_CN-cpf-2.05-ff", "cpf-2.05-ff")
_add_alias("kr_KR-cpf-2.05-ff", "cpf-2.05-ff")


# ----------------------------------------------------------------------
# CPFD aliases
# ----------------------------------------------------------------------
_add_alias("zn_CN-cpfd-2.05-ff", "cpfd-2.05-ff")
_add_alias("zh_CN-cpfd-2.05-ff", "cpfd-2.05-ff")
_add_alias("kr_KR-cpfd-2.05-ff", "cpfd-2.05-ff")


# ----------------------------------------------------------------------
# PMAT aliases
# ----------------------------------------------------------------------
_add_alias("zn_CN-pmat24-a-2.00-ff", "pmat24-a-2.00-ff")
_add_alias("zh_CN-pmat24-a-2.00-ff", "pmat24-a-2.00-ff")
_add_alias("kr_KR-pmat24-a-2.00-ff", "pmat24-a-2.00-ff")


# ----------------------------------------------------------------------
# PCET aliases
# ----------------------------------------------------------------------
_add_alias("zn_CN-k-pcet-3.00-ff", "k-pcet-3.00-ff")
_add_alias("zh_CN-k-pcet-3.00-ff", "k-pcet-3.00-ff")
_add_alias("kr_KR-k-pcet-3.00-ff", "k-pcet-3.00-ff")


# ----------------------------------------------------------------------
# SPCPTNL aliases
# ----------------------------------------------------------------------
_add_alias("zn_CN-spcptnl-2.01-ff", "spcptnl-2.01-ff")
_add_alias("zh_CN-spcptnl-2.01-ff", "spcptnl-2.01-ff")
_add_alias("kr_KR-spcptnl-2.01-ff", "spcptnl-2.01-ff")