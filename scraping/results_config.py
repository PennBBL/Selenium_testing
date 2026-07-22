from dataclasses import dataclass


@dataclass(frozen=True)
class ResultsConfig:
    test_name: str
    csv_file: str
    target_scores: list[str]


RESULTS_CONFIGS = {
    'k-er40-d-4.60-ff': ResultsConfig(
        test_name='k-er40-d-4.60-ff',
        csv_file='er40_results.csv',
        target_scores=['ScorVers', 'ER40D_CR', 'ER40D_RTCR', 'ER40D_LRSR'],
    ),
    'k-cpw-3.01-ff': ResultsConfig(
        test_name='k-cpw-3.01-ff',
        csv_file='cpw_results.csv',
        target_scores=['ScorVers', 'CPW_CR', 'CPW_PC', 'CPW_RTCR', 'CPW_TP'],
    ),
    'zn_CN-vsplot24-2.10-ff': ResultsConfig(
        test_name='zn_CN-vsplot24-2.10-ff',
        csv_file='vsplot_results.csv',
        target_scores=[
            'ScorVers',
            'VSPLOT24_CR',
            'VSPLOT24_PC',
            'VSPLOT24_RTCR',
            'VSPLOT24_ER',
            'VSPLOT24_RTER',
            'VSPLOT24_RT',
        ],
    ),
    "medf36-a-3.06-ff": ResultsConfig(
        test_name="medf36-a-3.06-ff",
        csv_file="medf_results.csv",
        target_scores=[
            "ScorVers",
            "MEDF36A_CR",
            "MEDF36A_PC",
            "MEDF36A_RTCR",
            "MEDF36A_ER"

            # add MEDF score names here
        ],
    ),
    "adt36-a-3.07-ff": ResultsConfig(
        test_name="adt36-a-3.07-ff",
        csv_file="adt_results.csv",
        target_scores=[
            "ScorVers",
            "ADT36A_CR",
            "ADT36A_PC",
            "ADT36A_RTCR",
            "ADT36A_ER",

            # add ADT score names here
        ],
    ),
    "mpraxis-2.06-ff": ResultsConfig(
        test_name="mpraxis-2.06-ff",
        csv_file="mpraxis_results.csv",
        target_scores=[
            "ScorVers",
            "MP1RT",
            "MP2",
            "MP2RTCR",
            "MP_EFF",
            # add Motor Praxis score names here once confirmed
        ],
    ),
    "svoltd-3.00-ff": ResultsConfig(
        test_name="svoltd-3.00-ff",
        csv_file="svoltd_results.csv",
        target_scores=[
            "ScorVers",
            # add SVOLTD score names once confirmed
        ],
    ),
    "cpf-2.05-ff": ResultsConfig(
        test_name="cpf-2.05-ff",
        csv_file="cpf_results.csv",
        target_scores=[
            "ScorVers",
            # add CPF score names once confirmed
        ],
    ),

    "cpfd-2.05-ff": ResultsConfig(
        test_name="cpfd-2.05-ff",
        csv_file="cpfd_results.csv",
        target_scores=[
            "ScorVers",
            # add CPFD score names once confirmed
        ],
    ),
    "pmat24-a-2.00-ff": ResultsConfig(
        test_name="pmat24-a-2.00-ff",
        csv_file="pmat_results.csv",
        target_scores=[
            "ScorVers",
            # add PMAT score names once confirmed
        ],
    ),
    "k-pcet-3.00-ff": ResultsConfig(
        test_name="k-pcet-3.00-ff",
        csv_file="pcet_results.csv",
        target_scores=[
            "ScorVers",
            # add PCET score names once confirmed
        ],
    ),
    "spcptnl-2.01-ff": ResultsConfig(
        test_name="spcptnl-2.01-ff",
        csv_file="spcptnl_results.csv",
        target_scores=[
            "ScorVers",
            # add SPCPTNL score names once confirmed
        ],
    ),
}

# Alias: some batteries expose VSPLOT without the language prefix.
RESULTS_CONFIGS['vsplot24-2.10-ff'] = RESULTS_CONFIGS['zn_CN-vsplot24-2.10-ff']



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


# CPW aliases
_add_alias("zn_CN-k-cpw-3.01-ff", "k-cpw-3.01-ff")
_add_alias("zh_CN-k-cpw-3.01-ff", "k-cpw-3.01-ff")

# VSPLOT aliases
_add_alias("vsplot24-2.10-ff", "zn_CN-vsplot24-2.10-ff")

# MPraxis aliases
_add_alias("zn_CN-mpraxis-2.06-ff", "mpraxis-2.06-ff")
_add_alias("kr_KR-mpraxis-2.06-ff", "mpraxis-2.06-ff")

# CPF aliases
_add_alias("zn_CN-cpf-2.05-ff", "cpf-2.05-ff")

# PMAT aliases
_add_alias("zn_CN-pmat24-a-2.00-ff", "pmat24-a-2.00-ff")
_add_alias("zh_CN-pmat24-a-2.00-ff", "pmat24-a-2.00-ff")

# PCET aliases
_add_alias("zn_CN-k-pcet-3.00-ff", "k-pcet-3.00-ff")
_add_alias("zh_CN-k-pcet-3.00-ff", "k-pcet-3.00-ff")

# SPCPTNL aliases
_add_alias("zn_CN-spcptnl-2.01-ff", "spcptnl-2.01-ff")
_add_alias("zh_CN-spcptnl-2.01-ff", "spcptnl-2.01-ff")