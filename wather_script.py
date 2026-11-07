from datetime import datetime, timedelta
import os
import re
import time
import requests

# ================= 1. 設定區 =================
# 中央氣象署 API 授權碼
CWA_API_KEY = "CWA-XXXXXXXXXXXXXXXXXXXX"

# LINE Developers金鑰與 User ID
LINE_ACCESS_TOKEN = "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
USER_ID = "XXXXXXXXXXXXXXXXX"

# 預設地點
TARGET_LOCATION = "花蓮縣"
SCHEDULE_HOUR = 7  # 設定每天推播的時（24小時制，早上 7 點）
SCHEDULE_MINUTE = 0  # 設定每天推播的分(整點發布)
RAIN_THRESHOLD = 50 #降雨機率判斷標準


# ================= 2. 氣象局 API 資料處理 =================
def get_weather_data(location):
    url = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001"
    params = {
        "Authorization": CWA_API_KEY,
        "format": "JSON",
        "locationName": location,
    }
    headers = {"accept": "application/json"}
    response = requests.get(url, params=params, headers=headers)

    try:
        return response.json()
    except Exception:
        print(f" 氣象署 API 回傳錯誤 (HTTP {response.status_code})")
        return {}


def simplify_data(data):
    location_data = data["records"]["location"][0]
    weather_elements = location_data["weatherElement"]
    simplified_data = {"location": location_data["locationName"]}

    for element in weather_elements:
        element_name = element["elementName"]
        for time_item in element["time"]:
            start_time = time_item["startTime"]
            end_time = time_item["endTime"]

            if start_time not in simplified_data:
                simplified_data[start_time] = {}
            if end_time not in simplified_data[start_time]:
                simplified_data[start_time][end_time] = {}

            parameter = time_item["parameter"]
            parameter_str = parameter["parameterName"]
            if "parameterUnit" in parameter:
                parameter_str += f" {parameter['parameterUnit']}"

            simplified_data[start_time][end_time][element_name] = parameter_str
    return simplified_data


def get_current_weather(simplified_data):
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for start_time, end_dict in simplified_data.items():
            if start_time == "location":
                continue
            for end_time, weather_info in end_dict.items():
                if start_time <= now <= end_time:
                    return weather_info

        for start_time, end_dict in simplified_data.items():
            if start_time == "location":
                continue
            for end_time, weather_info in end_dict.items():
                return weather_info

    except Exception as e:
        print(f"解析資料錯誤: {e}")
    return None


def check_location_in_message(message):
    locations = [
        "臺北市",
        "臺中市",
        "臺南市",
        "高雄市",
        "新北市",
        "桃園市",
        "新竹市",
        "新竹縣",
        "苗栗縣",
        "彰化縣",
        "南投縣",
        "雲林縣",
        "嘉義市",
        "嘉義縣",
        "屏東縣",
        "宜蘭縣",
        "花蓮縣",
        "臺東縣",
        "澎湖縣",
        "金門縣",
        "連江縣",
    ]
    corrected_message = re.sub("台", "臺", message)
    for location in locations:
        if location in corrected_message or corrected_message in location:
            return location
    return "臺北市"


# ================= 3. LINE 發送訊息函式 =================
def send_line_message(message_text):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
    }
    payload = {"to": USER_ID, "messages": [{"type": "text", "text": message_text}]}

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        if res.status_code == 200:
            print(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✅ 已成功發送氣象至 LINE！"
            )
        else:
            print(f" LINE 發送失敗 ({res.status_code}): {res.text}")
    except Exception as e:
        print(f" 發送 LINE 訊息失敗：{e}")


def run_weather_job():
    """執行一次抓取與推播任務"""
    location = check_location_in_message(TARGET_LOCATION)
    print(f"\n 觸發定時任務：正在抓取【{location}】氣象...")

    weather_data = get_weather_data(location)

    if "records" in weather_data and weather_data["records"]["location"]:
        simplified_data = simplify_data(weather_data)
        current_weather = get_current_weather(simplified_data)

        if current_weather is not None:
            # 1. 取得降雨機率字串並轉為數字（定義 pop_val）
            pop_raw = str(current_weather.get("PoP", "0")).replace("百分比", "")
            try:
                pop_val = int(pop_raw)
            except ValueError:
                pop_val = 0

            pop_text = f"{pop_val}%"

            # 2. 組成基礎氣象簡訊
            line_message = (
                f"☀️ 早安！【{location} 今日氣象預報】\n"
                f"🌤 氣候：{current_weather.get('Wx', '無資料')}\n"
                f"🌡 氣溫：{current_weather.get('MinT', '')} - {current_weather.get('MaxT', '')}\n"
                f"🌧 降雨機率：{pop_text}\n"
                f"🧘 體感：{current_weather.get('CI', '無資料')}"
            )

            # 3. 判斷是否帶傘
            if pop_val >= RAIN_THRESHOLD:
                line_message += "\n\n☔️【貼心提醒】今日降雨機率較高，出門記得帶傘喔！"
            else:
                line_message += "\n\n😎 今日降雨機率低，可以放心地出門～"

            send_line_message(line_message)
        else:
            print("❌ 無法解析當前氣象資料。")
    else:
        print("❌ 無法取得氣象資料，請檢查 CWA API Key。")


# ================= 4. 自動排程核心迴圈 =================
if __name__ == "__main__":
    print(" 氣象自動推播服務已啟動！")

    # 啟動時先立即測試發送一次
    print("正在進行首次連線與測試發送...")
    run_weather_job()

    print(
        f"\n📌 已進入每日自動排程模式（設定時間：每天 {SCHEDULE_HOUR:02d}:{SCHEDULE_MINUTE:02d}）"
    )
    print("⚠️ 請保持此視窗或電腦為開機狀態。按 Ctrl+C 可停止服務。\n")

    while True:
        now = datetime.now()

        # 下一次目標時間
        target_time = now.replace(
            hour=SCHEDULE_HOUR,
            minute=SCHEDULE_MINUTE,
            second=0,
            microsecond=0,
        )

        # 如果今天的 07:00 已經過了，目標時間就順延到明天的 07:00
        if now >= target_time:
            target_time += timedelta(days=1)

        # 計算需要等待的秒數
        sleep_seconds = (target_time - now).total_seconds()
        print(
            f"🕒 下一次推播時間：{target_time.strftime('%Y-%m-%d %H:%M:%S')}（倒數 {int(sleep_seconds // 3600)} 小時 {int((sleep_seconds % 3600) // 60)} 分鐘）"
        )

        # 程式暫停等待到指定時間點
        time.sleep(sleep_seconds)

        # 時間到，執行任務
        run_weather_job()

        # 執行完畢後暫停 60 秒，避免極短時間內重複觸發
        time.sleep(60)
