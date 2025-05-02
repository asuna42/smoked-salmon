import json
from collections import defaultdict

from salmon.errors import ScrapeError
from salmon.sources import BeatportBase
from salmon.tagger.sources.base import MetadataMixin

# genres from https://api.beatport.com/v4/catalog/genres/?page=1&per_page=100
# subgenres not often used
SPLIT_GENRES = {
    "140 / Deep Dubstep / Grime": {"140bpm", "Deep Dubstep", "Grime"},
    "Afro House": {"Afro House"},
    "Amapiano": {"Amapiano"},
    "Ambient / Experimental": {"Ambient", "Experimental"},
    "Bass / Club": {"Bass", "Club"},
    "Bass House": {"Bass House"},
    "Brazilian Funk": {"Brazilian Funk"},
    "Breaks / Breakbeat / UK Bass": {"Breaks", "Breakbeat", "UK Bass"},
    "Dance / Pop": {"Dance", "Pop"},
    "Deep House": {"Deep House"},
    "DJ Tools": {"DJ Tool"},
    "Downtempo": {"Downtempo"},
    "Drum & Bass": {"Drum and Bass"},
    "Dubstep": {"Dubstep"},
    "Electro (Classic / Detroit / Modern)": {"Electro"},
    "Electronica": {"Electronica"},
    "Funky House": {"Funky House"},
    "Hard Dance / Hardcore / Neo Rave": {"Hard Dance", "Hardcore Dance", "Neo Rave"},
    "Hard Techno": {"Hard Techno"},
    "House": {"House"},
    "Indie Dance": {"Indie Dance"},
    "Jackin House": {"Jackin House"},
    "Mainstage": {"Mainstage"},
    "Melodic House & Techno": {"Melodic House", "Techno"},
    "Minimal / Deep Tech": {"Minimal", "Deep Tech"},
    "Nu Disco / Disco": {"Nu Disco", "Disco"},
    "Organic House": {"Organic House"},
    "Progressive House": {"Progressive House"},
    "Psy-Trance": {"PsyTrance"},
    "Tech House": {"Tech House"},
    "Techno (Peak Time / Driving)": {"Techno"},
    "Techno (Raw / Deep / Hypnotic)": {"Techno", "Hypnotic Techno", "Deep Techno"},
    "Trance (Main Floor)": {"Trance", "Main Floor"},
    "Trance (Raw / Deep / Hypnotic)": {"Trance", "Deep", "Hypnotic)"},
    "Trap / Future Bass": {"Trap", "Future Bass"},
    "UK Garage / Bassline": {"UK Garage", "Bassline"},
}


class Scraper(BeatportBase, MetadataMixin):
    async def create_soup(self, url):
        """
        Override create_soup to properly get the album data from the API.
        This method uses the QobuzBase get_json method.
        """

        """
        Asynchroniously run a webpage scrape and return a BeautifulSoup
        object containing the scraped HTML.
        """
        soup = await super().create_soup(url)
        next_data = soup.find("script", id="__NEXT_DATA__")
        data = json.loads(next_data.encode_contents())
        try:
            release = data["props"]["pageProps"]["release"]
        except KeyError as err:
            raise ScrapeError(f"Could not find release data: {str(err)}") from err
        # Verify basic required fields exist
        if not release.get("name"):
            raise ScrapeError("Missing required field 'name' in Beatport NEXT_DATA")

        try:
            self.token = data["props"]["pageProps"]["anonSession"]["access_token"]
        except KeyError as err:
            raise ScrapeError(f"Could not find API token: {str(err)}") from err

        release["tracks"] = await self._fetch_tracks(release)
        return release

    async def _fetch_tracks(self, soup):
        """
        Fetch the track data from the Beatport API using the release id.
        """
        release_id = soup["id"]
        url = f"/v4/catalog/releases/{release_id}/tracks/?page=1&per_page=100"
        headers = {"Authorization": f"Bearer {self.token}"}

        try:
            response = await self.get_json(url, headers=headers)
        except Exception as err:
            raise ScrapeError(f"Failed to fetch track data from Beatport API: {str(err)}") from err

        if response["page"] != "1/1":
            raise ScrapeError("Only first 100 tracks could be fetched")

        return response["results"]

    def parse_release_title(self, soup):
        return soup["name"]

    def parse_cover_url(self, soup):
        return soup["image"]["uri"]

    def parse_genres(self, soup):
        genres = set({"Electronic"})
        for track in soup["tracks"]:
            try:
                genre = track["genre"]["name"]
            except KeyError as e:
                raise ScrapeError("Could not parse genre.") from e
            genres |= SPLIT_GENRES[genre]
        return genres

    def parse_release_year(self, soup):
        try:
            return int(soup["publish_date"].split("-")[0])
        except (TypeError, IndexError) as e:
            raise ScrapeError("Could not parse release year.") from e

    def parse_release_date(self, soup):
        try:
            return soup["publish_date"]  # YYYY-MM-DD
        except KeyError as e:
            raise ScrapeError("Could not parse release date.") from e

    def parse_release_label(self, soup):
        try:
            return soup["label"]["name"]
        except KeyError as e:
            raise ScrapeError("Could not parse record label.") from e

    def parse_release_catno(self, soup):
        try:
            return soup["catalog_number"]
        except KeyError as e:
            raise ScrapeError("Could not parse catalog number.") from e

    def parse_comment(self, soup):
        return None  # Comment does not exist.

    def parse_tracks(self, soup):
        tracks = defaultdict(dict)
        cur_disc = 1

        for track_num, track in enumerate(soup["tracks"], start=1):
            try:
                tracks[str(cur_disc)][track_num] = self.generate_track(
                    trackno=track_num,
                    discno=cur_disc,
                    artists=parse_artists(track),
                    title=parse_title(track),
                    isrc=track["isrc"],
                    streamable=track["is_available_for_streaming"],
                )
            except (ValueError, IndexError, KeyError) as e:
                raise ScrapeError(f"Could not parse tracks. {str(e)}") from e
        return dict(tracks)


def parse_title(track):
    """Add the remix string to the track title, as long as it's not OM."""
    title = track["name"]
    remix = track["mix_name"]
    if remix and remix != "Original Mix":  # yw pootsu
        title += f" ({remix})"
    return title


def parse_artists(track):
    """Parse remixers and main artists; return a list of them."""
    artists, remixers = [], []
    for artist in track["artists"]:
        artists.append(artist["name"])
    for remixer in track["remixers"]:
        remixers.append(remixer["name"])

    return [
        *((name, "main") for name in artists),
        *((name, "remixer") for name in remixers),
    ]
