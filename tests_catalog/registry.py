from tests_catalog.er40_plugin import ER40Plugin
from tests_catalog.cpw_plugin import CPWPlugin
from tests_catalog.vsplot_plugin import VSPLOTPlugin
from tests_catalog.medf_plugin import MEDFPlugin
from tests_catalog.adt_plugin import ADTPlugin
from tests_catalog.svoltd_plugin import SVOLTDPlugin
from tests_catalog.mpraxis_plugin import MPraxisPlugin
from tests_catalog.cpf_plugin import CPFPlugin
from tests_catalog.cpfd_plugin import CPFDPlugin
from tests_catalog.pmat_plugin import PMATPlugin
from tests_catalog.pcet_plugin import PCETPlugin
from tests_catalog.spcptnl_plugin import SPCPTNLPlugin
from tests_catalog.zn_spcptnl_plugin import ZN_SPCPTNLPlugin

TEST_REGISTRY = {
    "k-er40-d-4.60-ff": ER40Plugin,
    "k-cpw-3.01-ff": CPWPlugin,
    "zn_CN-k-cpw-3.01-ff": CPWPlugin,
    "zh_CN-k-cpw-3.01-ff": CPWPlugin,
    "zn_CN-vsplot24-2.10-ff": VSPLOTPlugin,
    "vsplot24-2.10-ff": VSPLOTPlugin,
    "medf36-a-3.06-ff": MEDFPlugin,
     # ADT
    "adt36-a-3.07-ff": ADTPlugin,
    "adt36-b-2.07-ff": ADTPlugin,
    "mpraxis-2.06-ff": MPraxisPlugin,
    "zn_CN-mpraxis-2.06-ff": MPraxisPlugin,
    "kr_KR-mpraxis-2.06-ff": MPraxisPlugin,
    "svoltd-3.00-ff": SVOLTDPlugin,
    "cpf-2.05-ff": CPFPlugin,
    "cpfd-2.05-ff": CPFDPlugin,
    "zn_CN-cpf-2.05-ff": CPFPlugin,
    "pmat24-a-2.00-ff": PMATPlugin,
    "zn_CN-pmat24-a-2.00-ff": PMATPlugin,
    "zh_CN-pmat24-a-2.00-ff": PMATPlugin,
    "k-pcet-3.00-ff": PCETPlugin,
    "zn_CN-k-pcet-3.00-ff": PCETPlugin,
    "zh_CN-k-pcet-3.00-ff": PCETPlugin,
    "spcptnl-2.01-ff": SPCPTNLPlugin,
    "zn_CN-spcptnl-2.01-ff": ZN_SPCPTNLPlugin,
    "zh_CN-spcptnl-2.01-ff": ZN_SPCPTNLPlugin,

}


DEFAULT_STRATEGIES = {
    "k-er40-d-4.60-ff": "random",
    "k-cpw-3.01-ff": "auto",
    "zn_CN-k-cpw-3.01-ff": "auto",
    "zh_CN-k-cpw-3.01-ff": "auto",
    "zn_CN-vsplot24-2.10-ff": "all_correct",
    "vsplot24-2.10-ff": "all_correct",
    "medf36-a-2.06_voice-ff": "correct",
    "adt36-a-3.07-ff": "random",
    "adt36-b-2.07-ff": "random",
    "mpraxis-2.06-ff": "coordinate",
    "zn_CN-mpraxis-2.06-ff": "coordinate",
    "kr_KR-mpraxis-2.06-ff": "coordinate",
    "svoltd-3.00-ff": "random",
    "cpf-2.05-ff": "random",
    "zn_CN-cpf-2.05-ff": "random",
    "cpfd-2.05-ff": "random",
    "pmat24-a-2.00-ff": "correct",
    "zn_CN-pmat24-a-2.00-ff": "correct",
    "zh_CN-pmat24-a-2.00-ff": "correct",
    "k-pcet-3.00-ff": "correct",
    "zn_CN-k-pcet-3.00-ff": "correct",
    "zh_CN-k-pcet-3.00-ff": "correct",
    "spcptnl-2.01-ff": "correct",
    "zn_CN-spcptnl-2.01-ff": "correct",
    "zh_CN-spcptnl-2.01-ff": "correct",
}