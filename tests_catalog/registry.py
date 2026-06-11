from tests_catalog.er40_plugin import ER40Plugin
from tests_catalog.cpw_plugin import CPWPlugin
from tests_catalog.vsplot_plugin import VSPLOTPlugin
from tests_catalog.medf_plugin import MEDFPlugin
from tests_catalog.adt_plugin import ADTPlugin


TEST_REGISTRY = {
    "k-er40-d-4.60-ff": ER40Plugin,
    "k-cpw-3.01-ff": CPWPlugin,
    "zn_CN-vsplot24-2.10-ff": VSPLOTPlugin,
    "vsplot24-2.10-ff": VSPLOTPlugin,
    "medf36-a-3.06-ff": MEDFPlugin,
     # ADT
    "adt36-a-3.07-ff": ADTPlugin,
    "adt36-b-2.07-ff": ADTPlugin,
}


DEFAULT_STRATEGIES = {
    "k-er40-d-4.60-ff": "random",
    "k-cpw-3.01-ff": "correct",
    "zn_CN-vsplot24-2.10-ff": "all_correct",
    "vsplot24-2.10-ff": "all_correct",
    "medf36-a-2.06_voice-ff": "correct",
    # ADT
    "adt36-a-3.07-ff": "random",
    "adt36-b-2.07-ff": "random",
}