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
    # ER40
    "k-er40-d-4.60-ff": ER40Plugin,

    # CPW
    "k-cpw-3.01-ff": CPWPlugin,
    "zn_CN-k-cpw-3.01-ff": CPWPlugin,
    "zh_CN-k-cpw-3.01-ff": CPWPlugin,
    "zn_CN-k-cpw-1.00-ff": CPWPlugin,

    # VSPLOT
    "vsplot24-2.10-ff": VSPLOTPlugin,
    "zn_CN-vsplot24-2.10-ff": VSPLOTPlugin,
    "zh_CN-vsplot24-2.10-ff": VSPLOTPlugin,
    "kr_KR-vsplot24-2.10-ff": VSPLOTPlugin,

    # MEDF
    "medf36-a-3.06-ff": MEDFPlugin,

    # ADT
    "adt36-a-3.07-ff": ADTPlugin,
    "adt36-b-2.07-ff": ADTPlugin,

    # MPraxis
    "mpraxis-2.06-ff": MPraxisPlugin,
    "zn_CN-mpraxis-2.06-ff": MPraxisPlugin,
    "zh_CN-mpraxis-2.06-ff": MPraxisPlugin,
    "kr_KR-mpraxis-2.06-ff": MPraxisPlugin,
    "zn_CN-k-mpraxis-2.06-ff": MPraxisPlugin,

    # SVolt / SVolt-D
    "svoltd-3.00-ff": SVOLTDPlugin,
    "zn_CN-k-svolt-3.01-ff": SVOLTDPlugin,

    # CPF
    "cpf-2.05-ff": CPFPlugin,
    "zn_CN-cpf-2.05-ff": CPFPlugin,
    "zh_CN-cpf-2.05-ff": CPFPlugin,
    "kr_KR-cpf-2.05-ff": CPFPlugin,

    # CPFD
    "cpfd-2.05-ff": CPFDPlugin,
    "zn_CN-cpfd-2.05-ff": CPFDPlugin,
    "zh_CN-cpfd-2.05-ff": CPFDPlugin,
    "kr_KR-cpfd-2.05-ff": CPFDPlugin,

    # PMAT
    "pmat24-a-2.00-ff": PMATPlugin,
    "zn_CN-pmat24-a-2.00-ff": PMATPlugin,
    "zh_CN-pmat24-a-2.00-ff": PMATPlugin,
    "kr_KR-pmat24-a-2.00-ff": PMATPlugin,

    # PCET
    "k-pcet-3.00-ff": PCETPlugin,
    "zn_CN-k-pcet-3.00-ff": PCETPlugin,
    "zh_CN-k-pcet-3.00-ff": PCETPlugin,
    "kr_KR-k-pcet-3.00-ff": PCETPlugin,

    # SPCPTNL
    "spcptnl-2.01-ff": SPCPTNLPlugin,
    "zn_CN-spcptnl-2.01-ff": ZN_SPCPTNLPlugin,
    "zh_CN-spcptnl-2.01-ff": ZN_SPCPTNLPlugin,
    "kr_KR-spcptnl-2.01-ff": ZN_SPCPTNLPlugin,

    # Not enabled yet: no plugin currently imported/available in this registry.
    # "zn_CN-slnb2-2.00-ff": SLNB2Plugin,
    # "zn_CN-slnb2-2.00-btn-ff": SLNB2Plugin,
    # "zn_CN-k-spvrt-d-1.00-ff": SPVRTPlugin,
    # "zn_CN-k-spvrt-d-1.05-ff": SPVRTPlugin,
}


DEFAULT_STRATEGIES = {
    # ER40
    "k-er40-d-4.60-ff": "random",

    # CPW
    "k-cpw-3.01-ff": "auto",
    "zn_CN-k-cpw-3.01-ff": "auto",
    "zh_CN-k-cpw-3.01-ff": "auto",
    "zn_CN-k-cpw-1.00-ff": "auto",

    # VSPLOT
    "vsplot24-2.10-ff": "all_correct",
    "zn_CN-vsplot24-2.10-ff": "all_correct",
    "zh_CN-vsplot24-2.10-ff": "all_correct",
    "kr_KR-vsplot24-2.10-ff": "all_correct",

    # MEDF
    "medf36-a-3.06-ff": "correct",

    # ADT
    "adt36-a-3.07-ff": "random",
    "adt36-b-2.07-ff": "random",

    # MPraxis
    "mpraxis-2.06-ff": "coordinate",
    "zn_CN-mpraxis-2.06-ff": "coordinate",
    "zh_CN-mpraxis-2.06-ff": "coordinate",
    "kr_KR-mpraxis-2.06-ff": "coordinate",
    "zn_CN-k-mpraxis-2.06-ff": "coordinate",

    # SVolt / SVolt-D
    "svoltd-3.00-ff": "random",
    "zn_CN-k-svolt-3.01-ff": "random",

    # CPF
    "cpf-2.05-ff": "random",
    "zn_CN-cpf-2.05-ff": "random",
    "zh_CN-cpf-2.05-ff": "random",
    "kr_KR-cpf-2.05-ff": "random",

    # CPFD
    "cpfd-2.05-ff": "random",
    "zn_CN-cpfd-2.05-ff": "random",
    "zh_CN-cpfd-2.05-ff": "random",
    "kr_KR-cpfd-2.05-ff": "random",

    # PMAT
    "pmat24-a-2.00-ff": "correct",
    "zn_CN-pmat24-a-2.00-ff": "correct",
    "zh_CN-pmat24-a-2.00-ff": "correct",
    "kr_KR-pmat24-a-2.00-ff": "correct",

    # PCET
    "k-pcet-3.00-ff": "correct",
    "zn_CN-k-pcet-3.00-ff": "correct",
    "zh_CN-k-pcet-3.00-ff": "correct",
    "kr_KR-k-pcet-3.00-ff": "correct",

    # SPCPTNL
    "spcptnl-2.01-ff": "correct",
    "zn_CN-spcptnl-2.01-ff": "correct",
    "zh_CN-spcptnl-2.01-ff": "correct",
    "kr_KR-spcptnl-2.01-ff": "correct",

    # Not enabled yet: no plugin currently imported/available in this registry.
    # "zn_CN-slnb2-2.00-ff": "correct",
    # "zn_CN-slnb2-2.00-btn-ff": "correct",
    # "zn_CN-k-spvrt-d-1.00-ff": "correct",
    # "zn_CN-k-spvrt-d-1.05-ff": "correct",
}
