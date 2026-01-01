"""QCrypt conference talk scraper."""
import re
from typing import List, Dict, Optional, Any
from .base import BaseTalkScraper


class QCryptTalkScraper(BaseTalkScraper):
    """Scraper for QCrypt invited/tutorial talks from schedule pages."""

    def get_url(self) -> str:
        """Return the URL for QCrypt schedule/program page."""
        # Use archive URL pattern from qcrypt.iaqi.org
        if self.year >= 2011:
            return f"https://qcrypt.iaqi.org/{self.year}/schedule/index.html"
        else:
            raise NotImplementedError(f"QCrypt {self.year} not supported")

    def parse_talk_data(self) -> List[Dict[str, Any]]:
        """Parse invited/tutorial talk data from QCrypt schedule HTML.

        QCrypt 2024 structure:
        <div class="session">
          <a href="../sessions/tutorial_xxx.html">
            <h4>Tutorial Talk: ''Title''</h4>
            <ul class="speakers">
              <li class="speaker">
                <strong class="speaker-name">Name</strong>
              </li>
            </ul>
          </a>
        </div>
        """
        talks = []

        # Find all h4 tags that contain talk titles
        for h4 in self.soup.find_all('h4'):
            h4_text = h4.get_text()

            # Check if this is an invited/tutorial/keynote talk
            if not self._is_special_talk_heading(h4_text.lower()):
                continue

            # Determine paper type
            paper_type = self.detect_paper_type(h4_text, '')

            # Extract title (remove the prefix "Tutorial Talk: " or "Invited Talk: ")
            title = re.sub(r'^(Tutorial|Invited|Keynote)\s+Talk:\s*[\'"]*(.*?)[\'"]* *$',
                          r'\2', h4_text, flags=re.IGNORECASE)
            title = self.normalize_title(title)

            # Find the parent <a> tag to get the session container
            parent_a = h4.find_parent('a')
            if not parent_a:
                # If no parent <a>, just use the h4 text
                talks.append({
                    'paper_type': paper_type,
                    'title': title,
                    'speakers': None,
                    'authors': None,
                    'affiliations': None,
                    'abstract': None,
                    'arxiv_ids': None,
                    'presentation_url': None,
                    'video_url': None,
                    'youtube_id': None,
                    'session_name': None,
                    'award': None,
                    'notes': 'No session container found'
                })
                continue

            # Extract speakers from <ul class="speakers">
            speakers = []
            speakers_ul = parent_a.find('ul', class_='speakers')
            if speakers_ul:
                for speaker_li in speakers_ul.find_all('li', class_='speaker'):
                    speaker_name_elem = speaker_li.find('strong', class_='speaker-name')
                    if speaker_name_elem:
                        speaker_name = self.normalize_name(speaker_name_elem.get_text())
                        if speaker_name:
                            speakers.append(speaker_name)

            # Get session URL (could be useful for notes)
            session_url = parent_a.get('href', '')

            # TODO: Could fetch the session detail page for abstract, arXiv, etc.
            # For now, we'll leave those empty and can be manually added

            talks.append({
                'paper_type': paper_type,
                'title': title,
                'speakers': speakers if speakers else None,
                'authors': None,  # Usually same as speakers for invited talks
                'affiliations': None,  # Not readily available in schedule page
                'abstract': None,  # Would need to fetch session detail page
                'arxiv_ids': None,  # Would need to fetch session detail page
                'presentation_url': None,
                'video_url': None,
                'youtube_id': None,
                'session_name': f"{paper_type.capitalize()} Talk",
                'award': None,
                'notes': f'Session URL: {session_url}' if session_url else None
            })

        return talks

    def _is_special_talk_heading(self, text: str) -> bool:
        """Check if heading indicates an invited/tutorial/keynote session."""
        keywords = [
            'invited talk', 'invited speaker',
            'tutorial talk', 'tutorial',
            'keynote', 'plenary',
            'distinguished lecture'
        ]
        return any(keyword in text for keyword in keywords)
