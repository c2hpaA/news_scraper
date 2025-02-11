import os
import time
import schedule
import subprocess

# **使用 venv 的 Python**
#PYTHON_EXECUTABLE = os.path.join("news_scraper_venv", "Scripts", "python.exe")

# 設定 spiders 目錄
VENV_DIR = "news_scraper_venv"
SPIDERS_DIR = os.path.join("news_scraper", "news_scraper", "spiders")
VENV_ACTIVATE = os.path.join(VENV_DIR, "Scripts", "activate.bat")
print("[INFO] SPIDERS_DIR:", SPIDERS_DIR)
#print("[INFO] PYTHON_EXECUTABLE:", PYTHON_EXECUTABLE)

#cd news_scraper\news_scraper\spiders && news_scraper_venv\Scripts\python.exe -m scrapy crawl money_udn_spider_v4 -a click_limit=5 -a article_limit=20 -a DEBUG=True
def activate_venv():
    """啟動虛擬環境"""
    print(f"[INFO] 啟動虛擬環境: {VENV_ACTIVATE}")
    subprocess.run(VENV_ACTIVATE, shell=True, check=True)

def run_money_udn_spider():
    print("[INFO] 執行 Scrapy money_udn_spider_v4")
    subprocess.run(
        f"cd {SPIDERS_DIR} && scrapy crawl money_udn_spider_v4 -a DEBUG=True",
        shell=True,
    )


def run_tfc_spider():
    print("[INFO] 執行 Scrapy tfc_spider")
    subprocess.run(
        f"cd {SPIDERS_DIR} && scrapy crawl tfc_spider -a DEBUG=True",
        shell=True,
    )

'''
def run_cofact_script():
    print("[INFO] 執行 cofact_script.py")
    subprocess.run(f"python {os.path.join(SPIDERS_DIR, 'cofact_script.py')}", shell=True)


def run_line_script():
    print("[INFO] 執行 line_script.py")
    subprocess.run(f"python {os.path.join(SPIDERS_DIR, 'line_script.py')}", shell=True)
'''
def run_cofact_script():
    """執行 cofact_script.py，先進入目錄再執行"""
    script_path = os.path.join(SPIDERS_DIR, "cofact_script.py")
    print(f"[INFO] 執行 cofact_script.py 路徑: {script_path}")
    
    command = f'cd /d "{SPIDERS_DIR}" && python cofact_script.py'
    subprocess.run(command, shell=True, check=True)

def run_line_script():
    """執行 line_script.py，先進入目錄再執行"""
    script_path = os.path.join(SPIDERS_DIR, "line_script.py")
    print(f"[INFO] 執行 line_script.py 路徑: {script_path}")
    
    command = f'cd /d "{SPIDERS_DIR}" && python line_script.py'
    subprocess.run(command, shell=True, check=True)


# 設定排程
schedule.every().day.at("14:00").do(run_money_udn_spider)
schedule.every().day.at("15:00").do(run_tfc_spider)
schedule.every().day.at("16:00").do(run_cofact_script)
schedule.every().day.at("16:30").do(run_line_script)

if __name__ == "__main__":
    #run_money_udn_spider()
    #run_tfc_spider()
    #run_cofact_script()
    #run_line_script()
    
    print("[INFO] 啟動定時任務...")
    while True:
        schedule.run_pending()
        time.sleep(60)  # 每 60 秒檢查一次
    