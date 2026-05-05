"""QIP conference talk scraper."""
from typing import List, Dict, Any
from .base import BaseTalkScraper


class QIPTalkScraper(BaseTalkScraper):
    """Scraper for QIP invited/tutorial talks."""

    def get_url(self) -> str:
        """Return the URL for the QIP program/schedule page."""
        # QIP 2026 has tutorials
        return f"https://qip.iaqi.org/{self.year}/programme/tutorial/index.html"

    def parse_talk_data(self) -> List[Dict[str, Any]]:
        """Parse QIP talk data from HTML.
        
        QIP 2026 uses ce-bodytext divs with paragraphs containing:
        - Speaker name in <strong> tags
        - Affiliation after <br>
        - Talk title in another <strong> tag
        - Abstract/description in following paragraphs
        """
        talks = []
        
        # Find all ce-bodytext sections
        body_sections = self.soup.find_all('div', class_='ce-bodytext')
        
        for section in body_sections:
            current_speaker = None
            current_affiliation = None
            current_title = None
            current_abstract_parts = []
            
            paragraphs = section.find_all('p')
            
            for p in paragraphs:
                text = p.get_text(strip=True)
                
                # Skip date headers
                if 'January' in text or 'Saturday' in text or 'Sunday' in text:
                    continue
                
                # Check for speaker name (has <strong> and <br>)
                strong_tags = p.find_all('strong')
                br_tags = p.find('br')
                
                # If we have accumulated a talk, save it before starting a new one
                if strong_tags and br_tags and current_speaker:
                    # Save previous talk
                    if current_speaker and current_title:
                        talks.append({
                            'title': current_title,
                            'abstract': ' '.join(current_abstract_parts).strip() if current_abstract_parts else None,
                            'speakers': [current_speaker],
                            'affiliations': [current_affiliation] if current_affiliation else [],
                            'paper_type': 'tutorial',
                            'topics': [],
                            'keywords': []
                        })
                    # Reset for new talk
                    current_speaker = None
                    current_affiliation = None
                    current_title = None
                    current_abstract_parts = []
                
                # Parse speaker and affiliation from paragraph with <br>
                if br_tags and strong_tags:
                    # Get HTML content
                    html = str(p)
                    import re
                    parts = re.split(r'<br\s*/?>', html)
                    
                    if len(parts) >= 2:
                        # First part has speaker name
                        from bs4 import BeautifulSoup
                        speaker_soup = BeautifulSoup(parts[0], 'html.parser')
                        speaker_strong = speaker_soup.find('strong')
                        if speaker_strong:
                            current_speaker = speaker_strong.get_text(strip=True)
                        
                        # Second part has affiliation
                        affil_soup = BeautifulSoup(parts[1], 'html.parser')
                        current_affiliation = affil_soup.get_text(strip=True)
                    continue
                
                # Check for talk title (paragraph with only <strong> tag)
                if strong_tags and len(strong_tags) == 1 and not br_tags:
                    potential_title = strong_tags[0].get_text(strip=True)
                    # Skip if it's empty, a date, or very short
                    if potential_title and len(potential_title) > 3 and not any(word in potential_title for word in ['January', 'Saturday', 'Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']):
                        current_title = potential_title
                    continue
                
                # Otherwise, it's abstract text (but check for meaningless strong tags)
                if text and len(text) > 20:
                    # Check if strong tags are just empty/whitespace
                    has_meaningful_strong = False
                    if strong_tags:
                        for st in strong_tags:
                            if st.get_text(strip=True):
                                has_meaningful_strong = True
                                break
                    
                    # If no meaningful strong tags, treat as abstract
                    if not has_meaningful_strong:
                        current_abstract_parts.append(text)
            
            # Save the last talk in this section
            if current_speaker and current_title:
                talks.append({
                    'title': current_title,
                    'abstract': ' '.join(current_abstract_parts).strip() if current_abstract_parts else None,
                    'speakers': [current_speaker],
                    'affiliations': [current_affiliation] if current_affiliation else [],
                    'paper_type': 'tutorial',
                    'topics': [],
                    'keywords': []
                })
        
        return talks
