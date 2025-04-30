import json

from salmon import config
from salmon.errors import ScrapeError
from salmon.search.base import IdentData, SearchMixin
from salmon.sources import BeatportBase


class Searcher(BeatportBase, SearchMixin):
    async def search_releases(self, searchstr, limit):
        releases = {}
        soup = await self.create_soup(self.search_url, params={"q": searchstr}, follow_redirects=True)

        next_data = soup.find("script", id="__NEXT_DATA__")
        data = json.loads(next_data.encode_contents())
        try:
            buildId = data["buildId"]
        except KeyError as err:
            raise ScrapeError(f"Could not find buildId: {str(err)}") from err

        url = f"https://www.beatport.com/_next/data/{buildId}/en/search/releases.json"
        resp = await self.get_json(url, params={"q": searchstr, "type": "releases"}, full_url=True)

        try:
            results = resp["pageProps"]["dehydratedState"]["queries"][0]["state"]["data"]["data"]
        except KeyError as err:
            raise ScrapeError(f"Could not find search results: {str(err)}") from err

        for result in results:
            try:
                rls_id = result["release_id"]
                ar_li = [a["artist_name"] for a in result["artists"]]
                title = result["release_name"]
                artists = ", ".join(ar_li) if len(ar_li) < 4 else config.VARIOUS_ARTIST_WORD
                label = result["label"]["label_name"]
                track_count = len(result["tracks"])
                year = result["release_date"].split("-")[0]
                catno = result["catalog_number"]
                if label.lower() not in config.SEARCH_EXCLUDED_LABELS:
                    releases[rls_id] = (
                        IdentData(artists, title, year, track_count, "WEB"),
                        # self.format_result(artists, title, label),
                        self.format_result(artists, title, f"{year} {label} {catno}", track_count),
                    )
            except (TypeError, IndexError) as e:
                raise ScrapeError("Failed to parse scraped search results.") from e
            if len(releases) == limit:
                break
        return "Beatport", releases
