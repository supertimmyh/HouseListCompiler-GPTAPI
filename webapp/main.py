import os
import base64
from typing import Union
from os.path import dirname, abspath, join
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# import packages for listing data extraction
import requests
from bs4 import BeautifulSoup
import re
import json

current_dir = dirname(abspath(__file__))
static_path = join(current_dir, "static")

app = FastAPI(title="Real Estate Listing API")
app.mount("/ui", StaticFiles(directory=static_path, html=True), name="ui")

class ListingRequest(BaseModel):
    url: str

class Body(BaseModel):
    length: Union[int, None] = 20


@app.get('/')
def root():
    html_path = join(static_path, "index.html")
    return FileResponse(html_path)

# Privacy Policy for GPT Actions
@app.get('/privacy-policy')
def privacy_policy():
    privacy_policy_path = join(static_path, "privacy_policy.html")
    return FileResponse(privacy_policy_path)

# listing data extraction start
# Function to search for the Matterport URL
def find_matterport_url(data):
    if isinstance(data, dict):
        for key, value in data.items():
            if key == 'home_tours' and isinstance(value, dict):
                virtual_tours = value.get('virtual_tours', [])
                for tour in virtual_tours:
                    if tour.get('category') == '3d' and 'href' in tour:
                        return tour['href']
            elif isinstance(value, (dict, list)):
                result = find_matterport_url(value)
                if result:
                    return result
    elif isinstance(data, list):
        for item in data:
            result = find_matterport_url(item)
            if result:
                return result
    return None

# Function to recursively search for the property details text
def find_property_description(data):
    if isinstance(data, dict):
        for key, value in data.items():
            # Looking for keys typically used for descriptions or details
            if key in ['description', 'details', 'text'] and isinstance(value, str):
                return value
            elif isinstance(value, (dict, list)):
                result = find_property_description(value)
                if result:
                    return result
    elif isinstance(data, list):
        for item in data:
            result = find_property_description(item)
            if result:
                return result
    return None

# Function to extract all dictionaries with the specified 'parent_category' values
def find_house_facts(data, parent_categories):
    # Convert the dictionary to a JSON string
    string_data = json.dumps(data)

    house_facts = []

    # Iterating over each parent category to find and extract relevant dictionaries
    for category in parent_categories:
        start_idx = 0
        while True:
            # Finding the next occurrence of the category within 'parent_category'
            start_idx = string_data.find(f'"parent_category": "{category}"', start_idx)
            if start_idx == -1:
                break  # No more occurrences found

            # Finding the start of the dictionary containing this 'parent_category'
            dict_start = string_data.rfind("{", 0, start_idx)
            if dict_start == -1:
                break  # Unable to find the start of the dictionary

            # Finding the end of the dictionary
            dict_end = string_data.find("}", start_idx)
            if dict_end == -1:
                break  # Unable to find the end of the dictionary

            # Extracting the dictionary string
            dict_string = string_data[dict_start:dict_end + 1]

            # Attempting to convert the dictionary string to a Python dictionary
            try:
                # Replacing single quotes and Python literals for JSON compatibility
                formatted_dict_string = dict_string.replace("'", '"').replace("None", "null").replace("False", "false").replace("True", "true")
                dict_data = json.loads(formatted_dict_string)
                house_facts.append(dict_data)
            except json.JSONDecodeError:
                # If there's an error in conversion, skip this dictionary
                pass

            # Updating the start index for the next search
            start_idx = dict_end

    return house_facts

def find_listing_info(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/",
            "DNT": "1",  # Do Not Track Request Header
            "Upgrade-Insecure-Requests": "1"
        }

        cookies = {
            "G_AUTHUSER_H": "0"
        }

        response = requests.get(url, headers=headers, cookies=cookies)

        if response.status_code == 200:
            results = {}
            soup = BeautifulSoup(response.content, 'html.parser')
            # Save HTML to a file for debug
            # with open('output.html', 'w', encoding='utf-8') as file:
            #     file.write(str(soup))
            
            # Find the address element using its 'data-testid' attribute
            address = soup.find('div', attrs={'data-testid': 'address-line-ldp'}).text.strip("View on Map")
            if address:
                print("The listing address: ", address)
            results['address'] = address

            # Find the all property details and links under the script tag
            script_tag = soup.find('script', id='__NEXT_DATA__')
            if script_tag:
                # Extract the JSON content from this script tag
                script_content = script_tag.string
                if script_content:
                    # Parse the JSON content
                    property_details = json.loads(script_content)
                    print("Property details and links founded")
                else:
                    print("No content found in the script tag")
            else:
                print("Script tag with ID '__NEXT_DATA__' not found")

            # Find the 3D tour link
            tour_link = find_matterport_url(property_details)
            print("3D Tour Link: ", tour_link) if tour_link else print("Unable to find 3D tour link")
            results['tour_link'] = tour_link

            # Find the house description
            house_descrp = find_property_description(property_details)
            print("House description found") if house_descrp else print("Unable to find house description")
            results['house_description'] = house_descrp

            # Find the src attribute of the first img tag within this div
            main_image = soup.find('img', class_='carousel-photo')
            if main_image and 'src' in main_image.attrs:
                main_image_url = main_image['src']
                print("Main Image URL:", main_image_url)
            else:
                print("Main image not found")
            results['main_iamge_link'] = main_image_url

            # Find house facts under parents categories
            categories = ["Community", "Exterior", "Features", "Interior", "Listing"]
            house_facts = find_house_facts(property_details, categories)
            print("House facts found: ", len(house_facts)) if house_facts else print("Unable to find house facts") # Displaying the count of extracted dictionaries
            results['house_facts'] = house_facts

            return results

        else:
            print(f"Failed to retrieve the webpage. Status code: {response.status_code}")
            return None

    except Exception as e:
        print(f"An error occurred: {e}")
        return None

# The listing results for social media posting
@app.post('/process-listing')
async def process_listing(request: ListingRequest):
    try:
        results = find_listing_info(request.url)
        if results:
            return results
        else:
            raise HTTPException(status_code=404, detail="Listing information not found.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))