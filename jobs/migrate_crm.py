"""Main Sequence Job: apply the CRM migrations before the CRM API and assistant roll out.

The deployment workflow in `.mainsequence/workflows/crm-api.yaml`, the
repository's only workflow file, runs this from the candidate image, so the
revisions it applies are the ones that image ships. A failure stops both
rollouts and the previous releases keep serving. A database already at head
still has its physical contracts checked and catalog bindings reconciled.

This repository owns one provider. Local development does not run this Job;
it runs `metatables --local migrations upgrade --provider
src.crm.migrations:migration` against the local SQLite runtime.
"""

import logging

from metatables import upgrade_application

# Every provider this repository owns, in dependency order.
PROVIDERS = ("src.crm.migrations:migration",)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    logging.getLogger("metatables.migrations.runner").setLevel(logging.INFO)
    for provider in PROVIDERS:
        result = upgrade_application(provider)
        state = "migrated" if result["migrated"] else "already current"
        print(
            f"{provider}: {result['revision']} ({state}; catalog reconciled) "
            f"on {result['data_source_uid']}",
            flush=True,
        )


if __name__ == "__main__":
    main()
