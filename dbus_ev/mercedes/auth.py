"""Interactive standalone login: python -m dbus_ev.mercedes.auth."""

import argparse
import asyncio
import getpass
from pathlib import Path

import aiohttp

from .oauth import Oauth
from .store import TokenStore
from .traffic import TrafficLimits
from .vendor.app_version import AppVersionManager
from .vendor.const import CONF_ALLOWED_REGIONS, REGION_CHINA


async def login(args):
    credentials_file = getattr(args, "credentials_file", "")
    if credentials_file and Path(credentials_file).resolve() == Path(args.token_file).resolve():
        raise ValueError("Credentials and tokens need separate files")
    store = TokenStore(args.token_file)
    store.acquire()
    try:
        limits = TrafficLimits(args.token_file)
        if limits.remaining():
            raise ValueError("Mercedes cooldown is active; wait before standalone login")
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            auth = Oauth(session, args.region, store, AppVersionManager(args.region))
            username = (await asyncio.to_thread(input, "Mercedes account email: ")).strip()
            password = await asyncio.to_thread(getpass.getpass, "Mercedes account password: ")
            await auth.async_login_new(username, password)
        limits.manual_login_succeeded()
        if credentials_file:
            TokenStore(credentials_file).save(
                {"username": username, "password": password, "region": args.region}
            )
            print("Authorization and private recovery credentials saved.")
        else:
            print("Authorization saved. Password was not stored.")
    except aiohttp.ClientResponseError as exc:
        if exc.status == 429:
            limits.rate_limited(exc)
        raise ValueError(f"Mercedes authentication HTTP {exc.status}; try later") from None
    finally:
        store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token-file", default="/data/setupOptions/dbus-ev/mercedes-token.json")
    parser.add_argument("--credentials-file", default="", help="Opt in to private login storage")
    parser.add_argument(
        "--region", choices=[r for r in CONF_ALLOWED_REGIONS if r != REGION_CHINA], default="Europe"
    )
    args = parser.parse_args()
    asyncio.run(login(args))


if __name__ == "__main__":
    main()
