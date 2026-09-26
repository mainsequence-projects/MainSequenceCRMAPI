"""Project-owned Tau CRM catalogue.

The SDK currently does not pass its validated caller to project extensions.
Consequently each tool fails closed until the host supplies a trusted runtime
provider; no model argument or process SDK credential can enable CRM access.
"""

from api.tau.crm_tools import build_crm_tools, unavailable_runtime


def setup(tau) -> None:
    for tool in build_crm_tools(unavailable_runtime):
        tau.register_tool(tool)
