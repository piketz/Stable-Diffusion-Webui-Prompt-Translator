# -*- coding: UTF-8 -*-
# This extension can translate prompt from your native language into English, so you can write prompt with your native language
# It uses online AI based tranlation service like deepl's API. So you need to get your own API Key from those service.
# Default translation service is Deepl, since it works better than Google and offers 500,000 free characters per month
# For Chinese users who can not use Deepl, it offers baidu translator.
# repo: https://github.com/butaixianran/
#
# How this works:
# Translation service's API can not be used by javascript in browser. There is a famous CORS issue. 
# So, we have to use those API at python side, then javascript can get the result. That means python extension must can be communicate with javascript side.
# There are 2 ways for that:
# 1. Create another http server in python, just for this extension. But that means this script never ends, and webui gonna be stopped there.
# 2. Ask webui's team offer more extension API, so extension can get prompt before user click generate button, no need javascript anymore.
# Maybe this can be done with some kind of hacking. And I do find a thing as:
# txt2img_prompt = modules.ui.txt2img_paste_fields[0][0]
# img2img_prompt = modules.ui.img2img_paste_fields[0][0]
# in modules.ui.
# But there is no document for that at all. And since it is a hacking, onece the ui changed, it won't work. And webui's UI changes a lot.
# So, that leads to the third, painful way:
# 3. Create some hidden textarea, buttons and toggles on extension's tab page. Javascript and python side both listen those components. 
# So, they can just turn toggle on and off, to tell each other come to get data.
# That's how this extension works now.


import modules.scripts as scripts
import gradio as gr
import os
import requests
import random
import hashlib
import json
import modules
from modules import script_callbacks
from scripts.services import GoogleTranslationService, yandex_translation as yt
import torch
from transformers import MarianMTModel, MarianTokenizer


# from modules import images
# from modules.processing import process_images, Processed
# from modules.processing import Processed
# from modules.shared import opts, cmd_opts, state


# Translation Service Providers
trans_providers = {
    "deepl": {
        "url":"https://api-free.deepl.com/v2/translate",
        "has_id": False
    },
    "baidu": {
        "url":"https://fanyi-api.baidu.com/api/trans/vip/translate",
        "has_id": True
    },
    "google": {
        "url":"https://translation.googleapis.com",
        "has_id": False
    },
    "yandex": {
        "url": "https://translate.api.cloud.yandex.net/translate/v2/translate",
        "has_id": True
    },
    "Helsinki-NLP": {
        "url": "",
        "has_id": False
    },
}
trans_H_NLP_models = ['es', 'de', 'fr', 'ru', 'ROMANCE', 'id', 'mul', 'zh', 'it', 'ar', 'nl', 'pl', 'fi', 'sv', 'vi',
                      'da', 'ja', 'ine', 'et', 'tr', 'roa', 'sla', 'bat', 'hi', 'ko', 'uk', 'hu', 'gmq', 'cs', 'ca',
                      'tc-big-it', 'sk', 'bg', 'eo', 'eu', 'tl', 'af', 'ur', 'th', 'tc-big-fr', 'sq', 'lv',
                      'tc-big-zle', 'mk', 'wa', 'az', 'ceb', 'cy', 'tc-big-he', 'mt', 'ga', 'grk', 'is', 'tc-big-el',
                      'gl', 'tc-big-ar', 'bn', 'tc-big-fi', 'jap', 'tc-big-lt', 'mr', 'bi', 'gem', 'ml', 'sm', 'mg',
                      'tc-big-cat_oci_spa', 'ka', 'ny', 'sn', 'pa', 'ng', 'aav', 'tc-big-tr', 'bcl', 'ht', 'hy', 'alv',
                      'war', 'yo', 'tc-big-sh', 'bem', 'mh', 'swc', 'dra', 'st', 'om', 'ho', 'kl', 'xh', 'ha', 'ig',
                      'tc-big-zls', 'fj', 'ilo', 'tc-big-ko', 'kg', 'ts', 'tc-big-et', 'ee', 'rw', 'tc-big-bg', 'lua',
                      've', 'iso', 'itc', 'tc-big-gmq', 'ase', 'nso', 'loz', 'gil', 'ber', 'yap', 'chk', 'sem', 'trk',
                      'zls', 'lg', 'sg', 'tc-big-lv', 'tn', 'tc-big-hu', 'lu', 'mkh', 'phi', 'run', 'pag', 'urj', 'lun',
                      'tpi', 'cau', 'kj', 'kqn', 'ln', 'lus', 'crs', 'gv', 'kab', 'ti', 'gaa', 'gmw', 'hil', 'iir',
                      'taw', 'umb', 'afa', 'cus', 'efi', 'lue', 'pis', 'ss', 'wal', 'tc-big-ces_slk', 'bzs', 'ccs',
                      'fiu', 'luo', 'niu', 'rn', 'bnt', 'cel', 'guw', 'mfe', 'toi', 'zle', 'cpp', 'mos', 'nic', 'srn',
                      'tiv', 'art', 'euq', 'kwn', 'pap', 'pon', 'pqe', 'rnd', 'wls', 'zlw', 'tc-big-cel', 'tc-big-zlw',
                      'cpf', 'inc', 'nyk', 'sal', 'to', 'tum', 'tvl', 'kwy', 'tll', 'opus-tatoeba-fi']

# user's translation service setting
trans_setting = {
    "deepl": {
        "is_default":True,
        "app_id": "",
        "app_key": ""
    },
    "baidu": {
        "is_default":False,
        "app_id": "",
        "app_key": ""
    },
    "google": {
        "is_default":False,
        "app_id": "",
        "app_key": ""
    },
    "yandex": {
        "is_default": True,
        "app_id": "",
        "app_key": ""
    },
    "Helsinki-NLP": {
        "is_default": False,
        "app_id": "",
        "app_key": "",
        "language_model": ""
    },

}

# user config file
# use scripts.basedir() to get current extension's folder
config_file_name = os.path.join(scripts.basedir(), "prompt_translator.cfg")


# on cpu
# def helsinki_trans(text):
#
#    translator = pipeline("translation", model="Helsinki-NLP/opus-mt-ru-en")
#    print(f'translator(text) : {translator(text)}')
#    return translator(text)[0]['translation_text']
#global model_helsinki
#global tokenizer_helsinki
model_helsinki = None
tokenizer_helsinki = None

def helsinki_trans(text):
    global model_helsinki
    global tokenizer_helsinki
    lang = trans_setting["Helsinki-NLP"]["language_model"]

    if not lang:
        return "Chose model lan in setting"

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    if not model_helsinki:
        model_name = f"Helsinki-NLP/opus-mt-{lang}-en"
        print(f'Load model... {model_name}')
        tokenizer_helsinki = MarianTokenizer.from_pretrained(model_name)
        model_helsinki = MarianMTModel.from_pretrained(model_name)
        model_helsinki.to(device)
    elif model_helsinki.device.type == "cpu":
            model_helsinki.to(device)

    inputs = tokenizer_helsinki(text, return_tensors="pt").to(device)
    outputs = model_helsinki.generate(**inputs)
    translated_text = tokenizer_helsinki.decode(outputs[0], skip_special_tokens=True)

    del inputs, outputs
    model_helsinki = model_helsinki.cpu()
    torch.cuda.empty_cache()

    return translated_text


# deepl translator
# refer: https://www.deepl.com/docs-api/translate-text/
# parameter: app_key, text
# return: translated_text
def deepl_trans(app_key, text):
    print("Getting data for deepl")
    # check error
    if not app_key:
        print("app_key can not be empty")
        return ""

    if not text:
        print("text can not be empty")
        return ""


    # set http request
    headers = {"Authorization": "DeepL-Auth-Key "+app_key}
    data ={
        "text":text,
        "target_lang":"EN"
    }

    print("Sending request")
    r = None
    try:
        r = requests.post(trans_providers["deepl"]["url"], data = data, headers = headers, timeout=10)
    except Exception as e:
        print("request get error, check your network")
        print(str(e))
        return ""

    print("checking response")
    # check error
    # refer: https://www.deepl.com/docs-api/api-access/general-information/
    if r.status_code >= 300 or r.status_code < 200:
        print("Get Error code from DeepL: " + str(r.status_code))
        if r.status_code == 429:
            print("too many requests")
        elif r.status_code == 456:
            print("quota exceeded")
        elif r.status_code >= 500:
            print("temporary errors in the DeepL service")

        print("check for more info: https://www.deepl.com/docs-api/api-access/general-information/")
        return ""

    # try to get content
    content = None
    try:
        content = r.json()

    except Exception as e:
        print("Parse response json failed")
        print(str(e))
        print("response:")
        print(r.text)
        return ""

    # try to get text from content
    translated_text = ""
    if content:
        if "translations" in content.keys():
            if len(["translations"]):
                if "text" in content["translations"][0].keys():
                    translated_text = content["translations"][0]["text"]

    if not translated_text:
        print("can not read tralstated text from response:")
        print(r.text)
        return ""

    return translated_text



# baidu translator
# refer: https://fanyi-api.baidu.com/doc/21
# parameter: app_id, app_key, text
# return: translated_text
def baidu_trans(app_id, app_key, text):
    print("Getting data for baidu")
    # check error
    if not app_id:
        print("app_id can not be empty")
        return ""

    if not app_key:
        print("app_key can not be empty")
        return ""

    if not text:
        print("text can not be empty")
        return ""

    # set http request
    salt = str(random.randint(10000,10000000))
    sign_str = app_id+text+salt+app_key
    sign_md5 = hashlib.md5(sign_str.encode("utf-8")).hexdigest()

    request_link = trans_providers["baidu"]["url"]+"?q="+text+"&from=auto&to=en&appid="+app_id+"&salt="+salt+"&sign="+sign_md5

    print("Sending request")
    r = None
    try:
        r = requests.get(request_link)
    except Exception as e:
        print("request get error, check your network")
        print(str(e))
        return ""

    # try to get content
    content = None
    try:
        content = r.json()

    except Exception as e:
        print("Parse response json failed")
        print(str(e))
        print("response:")
        print(r.text)
        return ""

    # check content error
    if not content:
        print("response content is empty")
        return ""

    if "error_code" in content.keys():
        print("return error for baidu:")
        print(content["error_code"])
        if "error_msg" in content.keys():
            print(content["error_msg"])
        print("response:")
        print(r.text)

        return ""

    # try to get text from content
    translated_text = ""
    if "trans_result" in content.keys():
        if len(content["trans_result"]):
            if "dst" in content["trans_result"][0].keys():
                translated_text = content["trans_result"][0]["dst"]

    if not translated_text:
        print("can not read translated text from response:")
        print(r.text)
        return ""

    return translated_text


# do translation
# parameter: provider, app_id, app_key, text
# return: translated_text
def do_trans(provider, app_id, app_key, text):
    print("====Translation start====")
    print("Use Serivce: " + provider)
    print("Source Prompt:")
    print(text)

    if provider not in trans_setting.keys():
        print("can not find provider: ")
        print(provider)
        return ""

    # translating
    translated_text = ""
    if provider == "deepl":
        translated_text = deepl_trans(app_key, text)
    elif provider == "baidu":
        translated_text = baidu_trans(app_id, app_key, text)
    elif provider == "google":
        service = GoogleTranslationService(app_key)
        translated_text = service.translate(text=text)
    elif provider == "yandex":
        translated_text = yt.yandex_trans(app_id, app_key, text)
    elif provider == "Helsinki-NLP":
        translated_text = helsinki_trans(text)
    else:
        print("can not find provider: ")
        print(provider)

    print("Translated result:")
    print(translated_text)

    return translated_text

# this is used when translating request is sending by js, not by a user's clicking
# in this case, we need a return like below:
# return: translated_text, translated_text, translated_text
# return it 3 times to send result to 3 different textbox.
# This is a hacking way to let txt2img and img2img get the translated result
def do_trans_js(provider, app_id, app_key, text): 
    print("Translating requested by js:")

    translated_text = do_trans(provider, app_id, app_key, text)

    print("return to both extension tab and txt2img+img2img tab")
    return [translated_text, translated_text, translated_text]
    



# send translated prompt to txt2img and img2img
def do_send_prompt(translated_text):
    return [translated_text, translated_text]



# save translation service setting
# parameter: provider, app_id, app_key
# return:
# trans_setting: a parsed json object as python dict with same structure as globel trans_setting object
def save_trans_setting(provider, app_id, app_key, new_sourse_lang=None):
    print("Saving tranlation service setting...")
    # write data into globel trans_setting
    global trans_setting

    # check error
    if not provider:
        print("Translation provider can not be none")
        return

    if provider not in trans_setting.keys():
        print("Translation provider is not in the list.")
        print("Your provider: " + provider)
        return

    if new_sourse_lang:
        if provider == 'yandex':
            yt.save_yandex_conf(None, None, new_sourse_lang)
        if provider == 'Helsinki-NLP':
            trans_setting[provider]["language_model"] = new_sourse_lang

    # set value    
    trans_setting[provider]["app_id"] = app_id
    trans_setting[provider]["app_key"] = app_key

    # set default
    trans_setting[provider]["is_default"] = True
    for prov in trans_setting.keys():
        if prov != provider:
            trans_setting[prov]["is_default"] = False

    # to json
    json_data = json.dumps(trans_setting)

    #write to file
    try:
        with open(config_file_name, 'w') as f:
            f.write(json_data)
    except Exception as e:
        print("write file error:")
        print(str(e))

    print("config saved to: " + config_file_name)

    

# load translation serivce setting
def load_trans_setting():
    # load data into globel trans_setting
    global trans_setting

    if not os.path.isfile(config_file_name):
        print("no config file: " + config_file_name)
        return

    with open(config_file_name, 'r') as f:
        data = json.load(f)

    # check error
    if not data:
        print("load config file failed")
        return
    
    for key in trans_setting.keys():
        if key not in data.keys():
            print("can not find " + key +" section in config file")
            return

    # set value
    trans_setting = data
    return



def on_ui_tabs():
    # init
    load_trans_setting()

    # get saved default provide name
    provider_name = "deepl"
    for key in trans_setting.keys():
        if trans_setting[key]["is_default"]:
            provider_name = key
            break

    # convert dict to list for provider names
    providers = []
    for key in trans_providers.keys():
        providers.append(key)

    yt.read_yandex_conf()
    yandex_lang_list = yt.iam_token_setting['sourceLanguageCode'].split(',')

    # get prompt textarea
    # UI structure
    # check modules/ui.py, search for txt2img_paste_fields
    # Negative prompt is the second element
    txt2img_prompt = modules.ui.txt2img_paste_fields[0][0]
    txt2img_neg_prompt = modules.ui.txt2img_paste_fields[1][0]
    img2img_prompt = modules.ui.img2img_paste_fields[0][0]
    img2img_neg_prompt = modules.ui.img2img_paste_fields[1][0]

    # ====Event's function====
    def set_provider(provider):
        app_id_visible = trans_providers[provider]['has_id']
        if provider == "yandex":
            return [app_id.update(visible=app_id_visible, label="FOLDER_ID", value=trans_setting[provider]["app_id"]),
                    app_key.update(label="OAUTH_TOKEN", value=trans_setting[provider]["app_key"]),
                    s_lang.update(visible=True, value=yandex_lang_list[0])]
        elif provider == "Helsinki-NLP":
            return [app_id.update(visible=False,  value=trans_setting[provider]["app_id"]),
                    app_key.update(visible=False, value=trans_setting[provider]["app_key"]),
                    s_lang.update(visible=True, choices=trans_H_NLP_models, value=trans_setting[provider]["language_model"])]
        else:
            return [app_id.update(visible=app_id_visible, label="APP ID", value=trans_setting[provider]["app_id"]),
                    app_key.update(label="APP KEY", value=trans_setting[provider]["app_key"]),
                    s_lang.update(visible=False, value=yandex_lang_list[0])]



    with gr.Blocks(analytics_enabled=False) as prompt_translator:
        # ====ui====
        gr.HTML("<p style=\"margin-bottom:0.75em\">It will translate prompt from your native language into English. So, you can write prompt with your native language.</p>")
        # gr.HTML("<br />")
        
        # Prompt Area
        with gr.Row():
            prompt = gr.Textbox(label="Prompt", lines=3, value="", elem_id="pt_prompt")
            translated_prompt = gr.Textbox(label="Translated Prompt", lines=3, value="", elem_id="pt_translated_prompt")

        with gr.Row():
            trans_prompt_btn = gr.Button(value="Translate", elem_id="pt_trans_prompt_btn")
            # add a hidden button, used by fake click with javascript. To simulate msg between server and client side.
            # this is the only way.
            trans_prompt_js_btn = gr.Button(value="Trans Js", visible=False, elem_id="pt_trans_prompt_js_btn")
            send_prompt_btn = gr.Button(value="Send to txt2img and img2img", elem_id="pt_send_prompt_btn")


        with gr.Row():
            neg_prompt = gr.Textbox(label="Negative Prompt", lines=2, value="", elem_id="pt_neg_prompt")
            translated_neg_prompt = gr.Textbox(label="Translated Negative Prompt", lines=2, value="", elem_id="pt_translated_neg_prompt")

        with gr.Row():
            trans_neg_prompt_btn = gr.Button(value="Translate", elem_id="pt_trans_neg_prompt_btn")
            # add a hidden button, used by fake click with javascript. To simulate msg between server and client side.
            # this is the only way.
            trans_neg_prompt_js_btn = gr.Button(value="Trans Js", visible=False, elem_id="pt_trans_neg_prompt_js_btn")
            send_neg_prompt_btn = gr.Button(value="Send to txt2img and img2img", elem_id="pt_send_neg_prompt_btn")


        gr.HTML("<hr />")

        # Translation Service Setting


        gr.HTML("<p style=\"margin-top:0.75em;font-size:20px\">Translation Service Setting</p>")
        provider = gr.Dropdown(choices=providers, value=provider_name, label="Provider", elem_id="pt_provider")
        app_id = gr.Textbox(label="APP ID", lines=1, value=trans_setting[provider_name]["app_id"], elem_id="pt_app_id")
        app_key = gr.Textbox(label="APP KEY", lines=1, value=trans_setting[provider_name]["app_key"], elem_id="pt_app_key")
        s_lang = gr.Dropdown(choices=yandex_lang_list, visible=False, value=yandex_lang_list[0], label="Sourse language", elem_id="pt_lang")
        save_trans_setting_btn = gr.Button(value="Save Setting")

        # yandex need sourse_lang and app_id as folder_id
        if provider_name == "yandex" or provider_name == "Helsinki-NLP":
            s_lang.visible = True
        # deepl do not need appid

        app_id.visible = trans_providers[provider_name]['has_id']

        # ====events====
        # Prompt
        trans_prompt_btn.click(do_trans, inputs=[provider, app_id, app_key, prompt], outputs=translated_prompt)
        trans_neg_prompt_btn.click(do_trans, inputs=[provider, app_id, app_key, neg_prompt], outputs=translated_neg_prompt)

        # Click by js
        trans_prompt_js_btn.click(do_trans_js, inputs=[provider, app_id, app_key, prompt], outputs=[translated_prompt, txt2img_prompt, img2img_prompt])
        trans_neg_prompt_js_btn.click(do_trans_js, inputs=[provider, app_id, app_key, neg_prompt], outputs=[translated_neg_prompt, txt2img_neg_prompt, img2img_neg_prompt])

        send_prompt_btn.click(do_send_prompt, inputs=translated_prompt, outputs=[txt2img_prompt, img2img_prompt])
        send_neg_prompt_btn.click(do_send_prompt, inputs=translated_neg_prompt, outputs=[txt2img_neg_prompt, img2img_neg_prompt])


        # Translation Service Setting

        provider.change(fn=set_provider, inputs=provider, outputs=[app_id, app_key, s_lang])
        save_trans_setting_btn.click(save_trans_setting, inputs=[provider, app_id, app_key, s_lang])

    # the third parameter is the element id on html, with a "tab_" as prefix
    return (prompt_translator , "Prompt Translator", "prompt_translator"),

script_callbacks.on_ui_tabs(on_ui_tabs)
