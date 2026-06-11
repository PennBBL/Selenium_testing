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
            "ADT36A_ER"

            # add ADT score names here
        ],
    ),
}

# Alias: some batteries expose VSPLOT without the language prefix.
RESULTS_CONFIGS['vsplot24-2.10-ff'] = RESULTS_CONFIGS['zn_CN-vsplot24-2.10-ff']