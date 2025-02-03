import csv
import requests
from bs4 import BeautifulSoup
import urllib.parse
import re
import time

def get_twitter_handle(name):
    query = name
    # Encode the query string
    query = urllib.parse.quote(query)
    url = f"https://html.duckduckgo.com/html/?q={query}"

    # print(url)

    headers = {
        'User-Agent': 'Mozilla/5.0'
    }

    try:
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Find all result links
        links = soup.find_all('a', href=True)
        if links:
            print(links)
        else:
            print("no links")

        for link in links:
            # print("links for " + name)
            # print(links)
            href = link['href']
            unquoted_href = urllib.parse.unquote(href)
            # Check if the link is a Twitter profile
            if 'twitter.com/' in unquoted_href and '/status/' not in unquoted_href:
                # print(unquoted_href)
                # Extract the Twitter handle
                match = re.search(r'twitter\.com/([^/?&]+)', unquoted_href)
                if match:
                    handle = match.group(1)
                    # Remove '&' and anything after it in the handle
                    handle = handle.split('&')[0]
                    # Optional: Verify if the name is in the handle or link text
                    # link_text = link.get_text().lower()
                    # if name.lower() in link_text or name.lower().replace(' ', '') in handle.lower():
                    #     # Construct the profile URL
                    profile_url = f"https://twitter.com/{handle}"
                    return handle, profile_url
        return None, None
    except Exception as e:
        print(f"An error occurred while processing '{name}': {e}")
        return None, None

def remove_middle_name(name):
    parts = name.split()
    if len(parts) > 2:
        # Remove the middle name/initial
        return f"{parts[0]} {parts[-1]}"
    else:
        return name

# Input and output CSV file names
input_csv = '/Users/jordanb/Downloads/Columbia Directory - Columbia College.csv'
output_csv = 'output_names_with_twitter.csv'

# Read names from the input CSV
with open(input_csv, 'r', encoding='utf-8') as csvfile_in:
    reader = csv.DictReader(csvfile_in)
    fieldnames = reader.fieldnames + ['Twitter Handle', 'Twitter Profile URL']
    rows = []
    x = 0

    for row in reader:
        original_name = row['Names from the University Bulletin']
        handles = []
        profile_urls = []

        # First, search with the original name
        handle, profile_url = get_twitter_handle(original_name)
        if handle and profile_url:
            handles.append(handle)
            profile_urls.append(profile_url)
            # Print the name and handle
            print(f"{original_name} - @{handle}")
        else:
            print(f"No Twitter handle found for '{original_name}'.")
        

        # If the name has a middle name/initial, search without it
        name_without_middle = remove_middle_name(original_name)
        if name_without_middle != original_name:
            handle2, profile_url2 = get_twitter_handle(name_without_middle)
            if handle2 and profile_url2:
                # Avoid duplicates
                if handle2 not in handles:
                    handles.append(handle2)
                    profile_urls.append(profile_url2)
                    # Print the name and handle
                    print(f"{name_without_middle} - @{handle2}")
            else:
                print(f"No Twitter handle found for '{name_without_middle}'.")

        if handles:
            # Join multiple handles and URLs with a semicolon
            row['Twitter Handle'] = '; '.join(handles)
            row['Twitter Profile URL'] = '; '.join(profile_urls)
            rows.append(row)

        # Polite delay to avoid overloading the server
        time.sleep(1)

        print(x)
        x += 1

if rows:
    with open(output_csv, 'w', encoding='utf-8', newline='') as csvfile_out:
        writer = csv.DictWriter(csvfile_out, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Twitter handles and profile URLs have been added to '{output_csv}'.")
else:
    print("No Twitter handles were found for any of the names.")