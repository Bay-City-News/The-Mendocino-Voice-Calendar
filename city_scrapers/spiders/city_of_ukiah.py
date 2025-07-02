import json
from datetime import datetime

import scrapy
from city_scrapers_core.constants import BOARD
from city_scrapers_core.items import Meeting


class CityUkiahApiSpider(scrapy.Spider):
    name = "city_ukiah_api"
    agency = "City of Ukiah"
    timezone = "America/Los_Angeles"

    # CivicClerk base API
    meetings_url = "https://ukiahca.api.civicclerk.com/v1/Meetings/ListMeetings"
    files_url_template = (
        "https://ukiahca.api.civicclerk.com/v1/Meetings/GetMeetingFiles?meetingId={}"
    )

    def start_requests(self):
        # This fetches meetings from 2024 to 2026
        payload = {
            "StartDate": "2024-01-01T00:00:00Z",
            "EndDate": "2026-01-01T00:00:00Z",
        }
        yield scrapy.Request(
            self.meetings_url,
            method="POST",
            body=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            callback=self.parse_meetings,
        )

    def parse_meetings(self, response):
        meetings = response.json()
        for meeting in meetings:
            meeting_id = meeting.get("id")
            if not meeting_id:
                continue

            # Use Metadata for make file links
            meta = {
                "title": meeting.get("name"),
                "start": meeting.get("startDateTime"),
                "location": meeting.get("location", {}).get("name", ""),
                "meeting_id": meeting_id,
            }

            yield scrapy.Request(
                url=self.files_url_template.format(meeting_id),
                callback=self.parse_files,
                meta=meta,
            )

    def parse_files(self, response):
        meta = response.meta
        links = []

        for f in response.json():
            file_id = f.get("fileId")
            title = f.get("name") or f.get("displayName") or "Document"
            if file_id:
                url = (
                    f"https://ukiahca.api.civicclerk.com/v1/Meetings/"
                    f"GetMeetingFileStream(fileId={file_id},plainText=false)"
                )

                links.append({"href": url, "title": title})

        start_dt = self._parse_datetime(meta["start"])

        meeting = Meeting(
            title=meta["title"],
            description="",
            classification=BOARD,
            start=start_dt,
            end=None,
            time_notes="",
            all_day=False,
            location={
                "name": "Ukiah Civic Center",
                "address": meta["location"] or "300 Seminary Ave, Ukiah, CA 95482",
            },
            links=links,
            source="https://cityofukiah.com/meetings/",  
            # Source site for public context
        )

        meeting["status"] = self._get_status(meeting)
        meeting["id"] = self._get_id(meeting)
        yield meeting

    def _parse_datetime(self, dt_str):
        # CivicClerk has a specific datetime format
        if not dt_str:
            return None
        return datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%SZ")

    def _get_status(self, meeting):
        if meeting["start"] and meeting["start"] > datetime.utcnow():
            return "tentative"
        return "passed"

    def _get_id(self, meeting):
        # Generate a unique ID using timestamp and title
        dt_str = meeting["start"].strftime("%Y%m%d%H%M")
        return f"{self.name}_{dt_str}_{meeting['title'].lower().replace(' ', '_')[:20]}"
