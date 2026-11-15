import base64
import re
import unicodedata

from pathlib import Path
from pypdf import PdfReader

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.print_page_options import PrintOptions as PO
from selenium.webdriver.support import expected_conditons as EC
from selenium.webdriver.support.ui import WebDriverWait

# global config constants
PDF_DIR, CSV_DIR, OUT_DIR = Path("pdf"), Path("csv"), Path("worksheets")
CSV_DIR.mkdir(exist_ok = True)
OUT_DIR.mkdir(exist_ok = True)
URL = "https://www.an2.net/tools/worksheet/mixed"

WORDS_PER_SHEET = 50
KEEP_DUPLICATES = True
SHEET_PAUSE =  10

VOCAB_ENTRY = re.compile(r"(\d{1,4}) ([一-鿿]+)")

def hsk_level(name: str) -> str:
    """Grab HSK level from PDF name"""
    return re.search(r"L(?:evel)?-?(\d+(?:-\d+)?)$", name).group(1)

def sort_key(path: Path) -> int:
    """Grab HSK levels as single-digit truncated keys for sorted()"""
    return int(re.search(r"\d+", path.stem).group())

def extract_words(pdf_path: Path) -> list[str]:
    """Extract text from PDF files and normalise Kangxi radicals as normal CJK Unicode block characters"""
    text = "\n".join(page.extract_text() or "" for page in PdfReader(pdf_path).pages)

    # normalise Kangxi radicals
    text = unicodedata.normalize("NKFC", text)
    int(re.search(r"\d+", path.stem).group())int(re.search(r"\d+", path.stem).group())
    words, expected = [], 1
    for num, word in VOCAB_ENTRY.findall(text):
        if int(num) == expected:
            words.append(word)
            expected += 1

    return words if KEEP_DUPLICATES else list(dict.fromkeys(words))

# extract CJK characters from PDF and write to CSV
for pdf_path in PDF_DIR.glob("*.pdf"):
    words = extract_words(pdf_path)

    csv_path =  CSV_DIR / f"HSK{hsk_level(pdf_path.stem)}.csv"
    csv_path.write_text(",".join(words), encoding = "utf-8")

    print(f"{pdf_path.name}: {len(words)} words -> {csv_path}")

# config for Firefox print-to-PDF dialog
print_options = PrintOptions()
print_options.page_width = 21.0
print_options.page_height = 29.7
print_options.background = True

options = webdriver.FirefoxOptions()
options.enable_bidi = True          # for add_preload_script
options.page_load_strategy = "none" # prevent print dialog from hanging Selenium

driver = webdriver.Firefox(options = options)
wait = WebDriverWait(driver, 30)

# window.print() is called as soon as worksheet is generated
# this opens a dialog that blocks Selenium
# add_preload_script here runs before any scripts on the site so the PDF can be saved from the dialog
driver.script.add_preload_script("() => { window.print = () => {}; }")

# generate PDF worksheets
try:
    for csv_path in sorted(CSV_DIR.glob("HSK*.csv"), key = sort_key):
        words = csv_path.read_text(encoding = "utf-8").split(",")

        # group characters into batches of size WORDS_PER_SHEET
        batches = [words[i:(i + WORDS_PER_SHEET)] for i in range(0, len(words), WORDS_PER_SHEET)]

        for n, batch in enumerate(batches, start = 1):
            out = OUT_DIR / f"{csv_path.stem}_{n:04d}.pdf"

            # skip existing generated PDFs
            if out.exists():
                continue

            driver.get(URL)
            form_tab = driver.current_window_handle

            # send batch to site text box
            text_box = wait.until(EC.presence_of_element_located((By.ID, "hzbox")))
            text_box.clear()
            text_box.send_keys(",".join(batch))

            # set site options using JavaScript so relevant elements can be selected
            driver.execute_script("""
                document.querySelector("input[name='types'][value='2']").click();  // 米字格
                document.getElementById('tzgbt').value = arguments[0];             // page header
                """, f"{csv_path.stem} · {n}/{len(batches)}")

            # generate Pinyin
            driver.execute_script("document.getElementById('generatePinyin').click();")

            # Pinyin is ready once pinyin box has been filled in after Pinyin has been generated
            wait.until(lambda d: d.find_element(By.ID, "pybox").get_attribute("value").strip())
            wait.until(EC.visibility_of_element_located((By.ID, "submitPrint")))

            # site has target="_blank", so generating a worksheet opens a new tab
            # switch to new tab when it opens
            driver.execute_script("document.getElementById('submitPrint').click();")
            wait.until(EC.number_of_windows_to_be(2))
            driver.switch_to.window(next(h for h in driver.window_handles if h != form_tab))

            # wait for new tab to fully load
            wait.until(lambda d: d.execute_script(
                "return document.readyState === 'complete' && document.fonts.status === 'loaded'"))
            time.sleep(1)

            # save generated worksheet as PDF
            out.write_bytes(base64.b64decode(driver.print_page(print_options)))
            print(f"saved {out}  ({'、'.join(batch)})")

            # close the new tab opened by generating a worksheet
            # and return to previous site tab
            driver.close()
            driver.switch_to.window(form_tab)
            time.sleep(PAUSE_BETWEEN_SHEETS)
finally:
    driver.quit()   # close Selenium browser window
