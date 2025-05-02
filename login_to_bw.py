import datetime
import calendar
import time
import sys
import getpass
import re

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

def click_accept_cookies(driver, timeout=10):
    try:
        btn = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
        )
        btn.click(); print("✅ Accepted cookies via OneTrust ID"); return
    except TimeoutException: pass
    try:
        btn = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((
                By.XPATH,
                "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'accept') "
                "and contains(., 'cookie')]"
            ))
        )
        btn.click(); print("✅ Accepted cookies via generic XPath")
    except TimeoutException:
        print("⚠️ No cookies prompt found")

def click_consumer_research(driver, timeout=20):
    def tile_exists(drv):
        return drv.execute_script("""
            function exists(root) {
              for (const a of root.querySelectorAll('a')) {
                if (a.textContent.trim().includes('Consumer Research')) return true;
              }
              for (const el of root.querySelectorAll('*')) {
                if (el.shadowRoot && exists(el.shadowRoot)) return true;
              }
              return false;
            }
            return exists(document);
        """)
    print("…waiting for Consumer Research tile…")
    WebDriverWait(driver, timeout).until(tile_exists)
    print("🎉 Found tile; clicking…")
    driver.execute_script("""
        function clickTile(root) {
          for (const a of root.querySelectorAll('a')) {
            if (a.textContent.trim().includes('Consumer Research')) {
              a.scrollIntoView({block:'center'});
              a.click();
              return true;
            }
          }
          for (const el of root.querySelectorAll('*')) {
            if (el.shadowRoot && clickTile(el.shadowRoot)) return true;
          }
          return false;
        }
        if (!clickTile(document)) throw 'Consumer Research tile not found at click time';
    """)
    print("✅ Clicked Consumer Research")

def click_dashboards(driver):
    driver.execute_script("""
        function clickDash(root) {
          for (const a of root.querySelectorAll('a')) {
            if (a.href.includes('/dashboards')) {
              a.scrollIntoView({block:'center'});
              a.click();
              return true;
            }
          }
          for (const el of root.querySelectorAll('*')) {
            if (el.shadowRoot && clickDash(el.shadowRoot)) return true;
          }
          return false;
        }
        if (!clickDash(document)) throw 'Dashboards link not found';
    """)
    print("✅ Clicked Dashboards menu item")

def login_to_brandwatch(email, password, max_retries=3):
    chrome_options = webdriver.ChromeOptions()
    driver = webdriver.Chrome(options=chrome_options)
    driver.maximize_window()
    driver.get(
        "https://login.brandwatch.com/login"
        "?client_id=my-brandwatch-prod-client"
        "&interactionUid=4KnWs-oUTHM19K0nJrES4"
        "&product_code=mybrandwatch"
    )
    wait = WebDriverWait(driver, 15)
    for attempt in range(1, max_retries + 1):
        print(f"=== Login attempt {attempt} ===")
        email_input = wait.until(EC.presence_of_element_located((By.NAME, "email")))
        email_input.clear(); email_input.send_keys(email)
        pwd_input = wait.until(EC.presence_of_element_located((By.NAME, "password")))
        pwd_input.clear(); pwd_input.send_keys(password, Keys.ENTER)
        print("Waiting for 2 seconds after login submit…")
        time.sleep(2)
        if "Sign in" not in driver.title:
            print("✅ Logged in"); break
        elif attempt == max_retries:
            print("⚠️ Max retries reached; check credentials")
    return driver

def select_location_dashboard(driver, location):
    title = f"{location} Antisemitism Trends from FCAS & JFNA"
    xpath = (
        f"//div[@class='ax-text--ellipsis' and normalize-space(text())='{title}']"
        "/ancestor::a[1]"
    )
    link = WebDriverWait(driver, 15).until(
        EC.element_to_be_clickable((By.XPATH, xpath))
    )
    link.click()
    print(f"→ Opened dashboard for {location}")

def process_location(driver, location):
    """
    1) Change date range to next month on the Introduction tab
    2) Bump the intro <h1> month
    3) Switch to "Conversations in {location}" and:
        a) bump that tab’s header <h1>
        b) adjust its bar-chart date range (previous year)
        c) bump its Top Posts <h2>
    4) Switch to "Conversations about {location}" and repeat steps a–c
    """
    import datetime, calendar, time
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    print(f"   • Processing {location}…")
    print("Waiting for 8 seconds…"); time.sleep(8)

    # --- 1) INTRO TAB: Change date range to next month ---
    dr_btn = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[aria-label="Change date range"]'))
    )
    dr_btn.click()
    print("Waiting for 1 seconds for the date picker…"); time.sleep(1)

    inp = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="dateRange"]'))
    )
    current = inp.get_attribute('value')
    start_str, _ = current.split(' - ')
    start_dt = datetime.datetime.strptime(start_str, '%b %d, %Y').date()
    year = start_dt.year + (start_dt.month // 12)
    month = (start_dt.month % 12) + 1
    first = datetime.date(year, month, 1)
    last  = datetime.date(year, month, calendar.monthrange(year, month)[1])
    new_range = f"{first.strftime('%b %d, %Y')} - {last.strftime('%b %d, %Y')}"
    inp.clear(); inp.send_keys(new_range)
    print(f"     – set intro date range to \"{new_range}\"")
    print("Waiting for 1 seconds…"); time.sleep(1)

    host = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'prisma-button.applyChanges'))
    )
    shadow = driver.execute_script("return arguments[0].shadowRoot", host)
    shadow.find_element(By.CSS_SELECTOR, 'button').click()
    print("     – clicked intro Apply")
    print("Waiting for 1 seconds…"); time.sleep(1)

    # --- 2) INTRO TAB: Open Quill and bump <h1> month ---
    WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, 'div.editicon.icon-pencil'))
    ).click()
    print("Waiting for 1 seconds for intro editor…"); time.sleep(1)

    editor_root = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.ID, "rich-text-editor-ql-editor-root"))
    )
    editor_root.click(); time.sleep(1)
    editor_root.find_element(By.CSS_SELECTOR, "div.ql-editor[contenteditable='true']").click()
    time.sleep(2)

    driver.execute_script("""
      const h1 = document.querySelector(
        '#rich-text-editor-ql-editor-root .ql-editor h1'
      );
      const months = ['JANUARY','FEBRUARY','MARCH','APRIL','MAY','JUNE',
                      'JULY','AUGUST','SEPTEMBER','OCTOBER','NOVEMBER','DECEMBER'];
      const parts = h1.textContent.trim().split(' ');
      const idx = months.indexOf(parts[0].toUpperCase());
      const next = months[(idx + 1) % 12];
      h1.textContent = next + ' ' + parts[1] + ' REPORT';
    """)
    print("     – bumped intro <h1> to next month")
    print("Waiting for 1 seconds…"); time.sleep(1)

    WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "button.js-apply"))
    ).click()
    print("     – clicked intro Done")
    print("Waiting for 5 seconds…"); time.sleep(1)

    # --- 3) CONVERSATIONS IN {location} ---
    print("Waiting for 2 seconds before switching tabs…"); time.sleep(2)
    WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.LINK_TEXT, f"Conversations in {location}"))
    ).click()
    print(f"     – switched to 'Conversations in {location}' tab")
    print("Waiting for 1 seconds…"); time.sleep(1)

    # a) Edit Conversations‐In header
    print("Waiting for 1 seconds before opening Conversations editor…"); time.sleep(1)
    conv_editable = None
    for editable in driver.find_elements(By.CSS_SELECTOR, "div.smallpadding.relative.editable.customtip"):
        try:
            note = editable.find_element(By.TAG_NAME, "uvl-destination-note")
            if "Online Conversations Originating" in note.get_attribute("data"):
                conv_editable = editable
                break
        except:
            continue
    if not conv_editable:
        raise Exception("❌ Could not locate the Conversations‐In note container")
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", conv_editable)
    conv_editable.click()
    print("Waiting for 1 seconds after opening Conversations editor…"); time.sleep(1)

    editor_root = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.ID, "rich-text-editor-ql-editor-root"))
    )
    editor_root.click(); time.sleep(2)
    editor_root.find_element(By.CSS_SELECTOR, "div.ql-editor[contenteditable='true']").click()
    time.sleep(3)

    driver.execute_script("""
      const h1 = document.querySelector(
        '#rich-text-editor-ql-editor-root .ql-editor h1'
      );
      const months = ['January','February','March','April','May','June',
                      'July','August','September','October','November','December'];
      const parts = h1.textContent.trim().split(' ');
      const current = parts.pop();
      const idx = months.findIndex(m => m.toLowerCase() === current.toLowerCase());
      const next = months[(idx + 1) % 12];
      h1.textContent = parts.join(' ') + ' ' + next;
    """)
    print("     – updated Conversations <h1> to next month")
    print("Waiting for 1 seconds…"); time.sleep(1)

    WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "button.js-apply"))
    ).click()
    print("     – clicked Conversations Done")
    print("Waiting for 1 seconds…"); time.sleep(1)

    # b) Adjust Conversations‐In bar‐chart date range
    # print("Waiting for 5 seconds before editing chart date range…"); time.sleep(5)
    range_span = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR,
            'div.componentHeader--section.dateRange span.value'
        ))
    )
    range_span.click()
    print("Waiting for 1 seconds for date picker…"); time.sleep(1)

    chart_inp = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="dateRange"]'))
    )
    val = chart_inp.get_attribute('value')
    start_str, end_str = val.split(' - ')
    sd = datetime.datetime.strptime(start_str, '%b %d, %Y').date()
    sd_prev = sd.replace(year=sd.year - 1)
    new_val = f"{sd_prev.strftime('%b %d, %Y')} - {end_str}"
    chart_inp.clear(); chart_inp.send_keys(new_val)
    print(f"     – set chart range to \"{new_val}\"")

    print("Waiting for 1 seconds before Apply…"); time.sleep(1)
    host = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'prisma-button.applyChanges'))
    )
    shadow = driver.execute_script("return arguments[0].shadowRoot", host)
    shadow.find_element(By.CSS_SELECTOR, 'button').click()
    print("     – clicked chart Apply")
    print("Waiting for 1 seconds…"); time.sleep(1)

    # c) Bump Conversations‐In Top Posts <h2>
    print("Waiting for 1 seconds before clicking Top Posts…"); time.sleep(1)
    driver.execute_script("""
      const notes = document.querySelectorAll("div.content.clearleft uvl-destination-note");
      const last = notes[notes.length - 1];
      last.scrollIntoView({block:'center'});
      last.click();
    """)
    print("Waiting for 1 seconds to inspect Top Posts…"); time.sleep(1)

    print("Waiting for 1 seconds before editing Top Posts content…"); time.sleep(1)
    editor_root = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.ID, "rich-text-editor-ql-editor-root"))
    )
    editor_root.click(); time.sleep(1)
    editor_root.find_element(By.CSS_SELECTOR, "div.ql-editor[contenteditable='true']").click()
    time.sleep(2)

    driver.execute_script("""
      const h2 = document.querySelector(
        '#rich-text-editor-ql-editor-root .ql-editor h2'
      );
      const months = ['January','February','March','April','May','June',
                      'July','August','September','October','November','December'];
      const parts = h2.textContent.trim().split(' ');
      const current = parts.pop();
      const idx = months.findIndex(m => m.toLowerCase() === current.toLowerCase());
      const next = months[(idx + 1) % 12];
      h2.textContent = parts.join(' ') + ' ' + next;
    """)
    print("     – bumped Top Posts <h2> to next month")
    print("Waiting for 1 seconds…"); time.sleep(1)

    WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "button.js-apply"))
    ).click()
    print("     – clicked Top Posts Done")
    print("Waiting for 1 seconds…"); time.sleep(1)

    # --- 4) CONVERSATIONS ABOUT {location} ---
    print("Waiting for 1 seconds before switching to 'about' tab…")
    time.sleep(1)
    tab_name = f"Conversations about {location}"
    driver.execute_script("""
    const text = arguments[0];
    const anchors = document.querySelectorAll('li.horizontal-navigation--item a[data-at="tab-name"]');
    for (const a of anchors) {
        if (a.textContent.trim() === text) {
        a.scrollIntoView({ block: 'center' });
        a.click();
        return;
        }
    }
    throw `Tab not found: ${text}`;
    """, tab_name)
    print(f"     – switched to '{tab_name}' tab")
    print("Waiting for 1 seconds…")
    time.sleep(1)

    # a) Edit Conversations-About header
    print("Waiting for 1 seconds before opening 'about' editor…")
    time.sleep(1)

    # 1) Locate the <uvl-destination-note> by part of its data attribute
    note = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((
            By.CSS_SELECTOR,
            "uvl-destination-note[data*='What People are Saying About']"
        ))
    )

    # 2) Scroll it into view & click it via JS
    driver.execute_script("""
    arguments[0].scrollIntoView({block: 'center'});
    arguments[0].click();
    """, note)

    print("Waiting for 1 seconds for 'about' editor to open…")
    time.sleep(1)

    # 3) Now wait for the Quill root to appear
    editor_root = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.ID, "rich-text-editor-ql-editor-root"))
    )
    print("✅ Editor popped up!")

    # 5) bump the <h1> month inside the editor
    driver.execute_script("""
    const h1 = document.querySelector(
        '#rich-text-editor-ql-editor-root .ql-editor h1'
    );
    if (!h1) throw 'About header <h1> not found!';
    const months = ['January','February','March','April','May','June',
                    'July','August','September','October','November','December'];
    const parts = h1.textContent.trim().split(' ');
    const current = parts.pop();
    const idx = months.findIndex(m => m.toLowerCase() === current.toLowerCase());
    const next = months[(idx + 1) % 12];
    h1.textContent = parts.join(' ') + ' ' + next;
    """)
    print("     – bumped 'about' Conversations header to next month")
    print("Waiting for 1 seconds…"); time.sleep(1)

    # 6) click Done
    WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "button.js-apply"))
    ).click()
    print("     – clicked 'about' Conversations Done")
    print("Waiting for 1 seconds…"); time.sleep(1)


    # — b) Adjust “About” bar‐chart date range —
    # print("Waiting for the About editor to finish closing…")
    # WebDriverWait(driver, 15).until(
    #     EC.invisibility_of_element_located((By.ID, "rich-text-editor-ql-editor-root"))
    # )

    # now find the About chart article (by either header text)
    chart_article = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.XPATH,
            '//article[contains(@class,"chartComponent") and ('
            'contains(.//h1,"Amount of Mentions Over the Past 13 Months") or '
            'contains(.//h1,"Mention Volume Over the Past 13 Months")'
            ')]'
        ))
    )
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", chart_article)
    print("  – scrolled to 'About' chart; waiting 2s…"); time.sleep(2)

    # click the date‐range span just like in the In tab
    range_span = chart_article.find_element(
        By.CSS_SELECTOR,
        'div.componentHeader--section.dateRange span.value'
    )

    # ← replace here ↓
    WebDriverWait(driver, 10).until(
        lambda d: range_span.is_displayed() and range_span.is_enabled()
    )
    driver.execute_script("arguments[0].click();", range_span)
    # ← end replacement ↑

    print("  – opened date picker; waiting 1s…"); time.sleep(1)

    # — grab the now‐visible <input>, scroll, click, clear & type —
    def _visible_date_input(drv):
        for inp in drv.find_elements(By.CSS_SELECTOR, 'input[name="dateRange"]'):
            if inp.is_displayed() and inp.is_enabled():
                return inp
        return False

    chart_inp = WebDriverWait(driver, 10).until(_visible_date_input)
    # scroll it into view & click to focus
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", chart_inp)
    chart_inp.click()
    time.sleep(1)

    # compute & send the new range
    old = chart_inp.get_attribute('value')
    start, end = [s.strip() for s in old.split(' - ', 1)]
    sd = datetime.datetime.strptime(start, '%b %d, %Y').date()
    new_start = sd.replace(year=sd.year - 1).strftime('%b %d, %Y')
    new_range = f"{new_start} - {end}"

    chart_inp.clear()
    chart_inp.send_keys(new_range)
    print(f"  – set 'About' chart range to “{new_range}”")
    time.sleep(2)

    # now click Apply in the shadow DOM
    host = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'prisma-button.applyChanges'))
    )
    driver.execute_script(
        "arguments[0].shadowRoot.querySelector('button').click()",
        host
    )
    print("  – clicked 'About' chart Apply")
    time.sleep(1)




    # c) Bump Conversations‐About Top Posts <h2>
    print("Waiting for 1 seconds before clicking 'about' Top Posts…"); time.sleep(1)

    driver.execute_script("""
      const notes = document.querySelectorAll("div.content.clearleft uvl-destination-note");
      const last = notes[notes.length - 1];
      last.scrollIntoView({block:'center'});
      last.click();
    """)
    print("Waiting for 1 seconds to inspect…"); time.sleep(1)

    print("Waiting for 1 seconds before editing 'about' Top Posts…"); time.sleep(1)
    editor_root = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.ID, "rich-text-editor-ql-editor-root"))
    )
    editor_root.click(); time.sleep(1)
    editor_root.find_element(By.CSS_SELECTOR, "div.ql-editor[contenteditable='true']").click()
    time.sleep(2)

    driver.execute_script("""
      const h2 = document.querySelector(
        '#rich-text-editor-ql-editor-root .ql-editor h2'
      );
      const months = ['January','February','March','April','May','June',
                      'July','August','September','October','November','December'];
      const parts = h2.textContent.trim().split(' ');
      const current = parts.pop();
      const idx = months.findIndex(m => m.toLowerCase() === current.toLowerCase());
      const next = months[(idx + 1) % 12];
      h2.textContent = parts.join(' ') + ' ' + next;
    """)
    print("     – bumped 'about' Top Posts <h2> to next month")
    print("Waiting for 1 seconds…"); time.sleep(1)

    WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "button.js-apply"))
    ).click()
    print("     – clicked 'about' Top Posts Done")
    print("Waiting for 1 seconds…"); time.sleep(1)



    # — Finally: Save (dry-run) —
    print("Waiting for 1 seconds…")
    time.sleep(1)

    print("Waiting for all editors to close…")
    WebDriverWait(driver, 15).until(
        EC.invisibility_of_element_located((By.ID, "rich-text-editor-ql-editor-root"))
    )

    print("Locating the Save button…")
    try:
        save_btn = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR,
                "button.js-save, button[data-at='dashboard-save']"
            ))
        )
        print("  – Save button found")

        # scroll the dashboard container (not window) back to top  
        container = driver.find_element(By.XPATH, "//*[@id='dashboard']/div")
        driver.execute_script("arguments[0].scrollTop = 0;", container)
        print("  – scrolled dashboard container to top")

        # DRY-RUN toggle
        DO_ACTUALLY_SAVE = True
        if DO_ACTUALLY_SAVE:
            try:
                save_btn.click()
                print("  – clicked Save")
            except:
                driver.execute_script("arguments[0].click();", save_btn)
                print("  – clicked Save via JS")
        else:
            print("⚠️ DRY RUN: skipping actual Save (set DO_ACTUALLY_SAVE = True to enable)")

    except TimeoutException:
        print("❌ Could not locate the Save button; check your selector")




    print(f"   ✔ Finished {location}")


def main():
    # 1) Prompt credentials + cities
    # email = input("Brandwatch email: ")
    # password = getpass.getpass("Brandwatch password: ")
    email = ""
    password = ""
    # location = input("Enter one location name: ").strip()
    # if not location:
    #     print("⚠️ No location entered; exiting."); return

    # expected = f"[location NAME] Antisemitism Trends from FCAS & JFNA"
    # if input(f"Is your dashboard still named “{expected}”? (y/n): ").lower() != 'y':
    #     print("❌ Script must be updated for your titles."); sys.exit(1)
    location = "Austin"

    driver = login_to_brandwatch(email, password)
    click_accept_cookies(driver)
    time.sleep(1)
    click_consumer_research(driver)

    WebDriverWait(driver, 10).until(lambda d: len(d.window_handles) > 1)
    driver.switch_to.window(driver.window_handles[-1])
    print("Waiting for 8 seconds…"); time.sleep(8)
    click_accept_cookies(driver)
    print("Waiting for 1 second…"); time.sleep(1)
    click_dashboards(driver)
    print("Waiting for 3 seconds…"); time.sleep(3)

    select_location_dashboard(driver, location)
    print("Waiting for 1 second…"); time.sleep(1)
    process_location(driver, location)

    print("🎉 Done with one location test!")
    print("Waiting for 30 seconds before quitting…"); time.sleep(30)
    driver.quit()

if __name__ == "__main__":
    main()







