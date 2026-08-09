import pathlib
import requests

url = "https://archives.nseindia.com/content/indices/ind_nifty200list.csv"
path = pathlib.Path(__file__).resolve().parent / "data" / "nifty200.csv"
path.parent.mkdir(parents=True, exist_ok=True)
response = requests.get(url, timeout=30)
response.raise_for_status()
path.write_text(response.text, encoding="utf-8")
print(path)
print("rows", len(response.text.splitlines()))
print("first", response.text.splitlines()[0])
