import modules.scripts as scripts
import os
import requests
import json

iam_token_setting = {
    "IAM_TOKEN": "",
    "expires_at": "",
    "sourceLanguageCode": "en, es, zh, fr, de, ja, ru, pt, it, ar, hi, ko, tr, pl, uk, nl, cs, sv, da, no"
}

config_iam_token = os.path.join(scripts.basedir(), "yandex_token.cfg")

def save_yandex_conf(IAM_TOKEN=None, expires_at=None, source_lang=None):
    with open(config_iam_token, "r") as f:
        data = json.load(f)

    if IAM_TOKEN:
        data['IAM_TOKEN'] = IAM_TOKEN
    if expires_at:
        data['expires_at'] = expires_at

    if source_lang:
        print(f'if source_lang: = {source_lang}')
        languages = list(set(data['sourceLanguageCode'].split(',')))
        if source_lang in languages:
            languages.remove(source_lang)
        languages.insert(0, source_lang)
        data['sourceLanguageCode'] = ','.join([l.strip() for l in languages])
        print(f'data[sourceLanguageCode] = {data["sourceLanguageCode"]}')

    with open(config_iam_token, "w") as f:
        json.dump(data, f)


def read_yandex_conf():
    global iam_token_setting
    with open(config_iam_token, "r") as f:
        data = json.load(f)
    # check error
    if not data:
        print("load config file failed")
        return

    for key in iam_token_setting.keys():
        if key not in data.keys():
            print("can not find " + key + " section in config file")
            return
    iam_token_setting = data
    return

# yandex translator
# refer: https://cloud.yandex.ru/docs/translate/operations/translate
# parameter: folder_id, oauth_token, text
# return: translated_text
def yandex_trans(folder_id, oauth_token, text):
    import datetime

    if not os.path.isfile(config_iam_token):
        with open(config_iam_token, "w") as f:
            json.dump(iam_token_setting, f)

    def get_iam_token(oauth_token, gettime=None):  # get active token
        url = 'https://iam.api.cloud.yandex.net/iam/v1/tokens'
        headers = {"Content-Type": "application/json"}
        data = {'yandexPassportOauthToken': oauth_token}
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            new_token = response.json()['iamToken']
            new_expiresAt = response.json()['expiresAt']
            save_yandex_conf(new_token, new_expiresAt)
        else:
            print(f"Get Error code: {response.status_code}")
            return None
        if gettime:
            return new_token, new_expiresAt
        else:
            return new_token

    print("Getting data for yandex")

    read_yandex_conf()
    # check error
    if not iam_token_setting['IAM_TOKEN']:
        get_iam_token(oauth_token)

    if not folder_id:
        return None

    if iam_token_setting['expires_at']:
        expiration_date = datetime.datetime.fromisoformat(iam_token_setting['expires_at'][:-7])
    else:
        IAM_TOKEN, new_expiresAt = get_iam_token(oauth_token, True)
        expiration_date = datetime.datetime.fromisoformat(new_expiresAt[:-7])

    if datetime.datetime.utcnow() > expiration_date:
        IAM_TOKEN = get_iam_token(oauth_token)
    else:
        IAM_TOKEN = iam_token_setting['IAM_TOKEN']

    body = {
        "sourceLanguageCode": iam_token_setting['sourceLanguageCode'].split(',')[0],
        "targetLanguageCode": 'en',
        "texts": [
            text
        ],
        "folderId": folder_id,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer {0}".format(IAM_TOKEN)
    }
    print("Sending request")
    r = None
    try:
        r = requests.post("https://translate.api.cloud.yandex.net/translate/v2/translate",
                          json=body,
                          headers=headers
                          )
    except Exception as e:
        print("request get error, check your network")
        print(str(e))
        return None

    print("checking response")
    if r.status_code >= 300 or r.status_code < 200:
        print("Get Error code: " + str(r.status_code))
        if r.status_code == 429:
            print("too many requests")
        elif r.status_code == 456:
            print("quota exceeded")
        elif r.status_code >= 500:
            print("temporary errors in the service")
        return None

    content = None
    try:
        content = r.json()

    except Exception as e:
        print("Parse response json failed")
        print(str(e))
        print("response:")
        print(r.text)

    translated_text = ""
    if content:
        if "translations" in content.keys():
            if len(["translations"]):
                if "text" in content["translations"][0].keys():
                    translated_text = content["translations"][0]["text"]

    if not translated_text:
        print("can not read tralstated text from response:")
        print(r.text)

    return translated_text
