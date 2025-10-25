import requests, os

url = "https://youtube-mp3-download1.p.rapidapi.com/dl"
headers = {
    "x-rapidapi-key": os.environ.get("RAPIDAPI_KEY"),
    "x-rapidapi-host": "youtube-mp3-download1.p.rapidapi.com"
}
params = {"id": "356OilwxvcY"}

r = requests.get(url, headers=headers, params=params)
print(r.status_code)
print(r.text)
