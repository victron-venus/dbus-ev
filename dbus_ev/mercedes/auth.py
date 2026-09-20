"""Interactive standalone login: python -m dbus_ev.mercedes.auth."""

import argparse
import asyncio
import getpass

import aiohttp

from .oauth import Oauth
from .store import TokenStore
from .vendor.app_version import AppVersionManager
from .vendor.const import CONF_ALLOWED_REGIONS, REGION_CHINA


async def login(args):
    store = TokenStore(args.token_file)
    store.acquire()
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            auth = Oauth(session, args.region, store, AppVersionManager(args.region))
            username = input("Mercedes account email: ").strip()
            password = getpass.getpass("Mercedes account password: ")
            await auth.async_login_new(username, password)
        print("Authorization saved. Password was not stored.")
    finally:
        store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token-file", default="/data/setupOptions/dbus-ev/mercedes-token.json")
    parser.add_argument(
        "--region", choices=[r for r in CONF_ALLOWED_REGIONS if r != REGION_CHINA], default="Europe"
    )
    args = parser.parse_args()
    asyncio.run(login(args))


if __name__ == "__main__":
    main()
