import main

def _instagram_profile(username: str) -> dict | None:
    sessionid = main.instagram_sessionid()
    return main.collect_profile(username, sessionid)

def _facebook_profile(slug: str, light: bool = False) -> dict | None:
    return None
