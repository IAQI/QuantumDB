"""QIP conference committee scraper."""
from typing import List, Dict
from .base import BaseCommitteeScraper


class QIPScraper(BaseCommitteeScraper):
    """Scraper for QIP conference committee pages."""
    
    def get_url(self) -> str:
        """Return the URL for QIP committee page."""
        # QIP 2026 has multiple pages for different committees
        # We'll scrape them individually
        return f"https://qip.iaqi.org/{self.year}/about/programme-committee/index.html"
    
    def parse_committee_data(self) -> List[Dict[str, str]]:
        """Parse committee data from QIP HTML.
        
        QIP 2026 uses paragraphs with <br> separated lists.
        Format: "Name, Affiliation<br />Name, Affiliation"
        """
        members = []
        
        # Find main content wrapper (QIP 2026 uses ce-bodytext class)
        main = self.soup.find('div', class_='ce-bodytext')
        if not main:
            return members
        
        # Get all paragraphs
        paragraphs = main.find_all('p')
        
        current_committee_type = None
        current_position = 'member'
        
        for p in paragraphs:
            # Check for section headers
            strong = p.find('strong')
            if strong:
                header_text = strong.get_text().lower()
                
                if 'program committee chair' in header_text or 'programme committee chair' in header_text:
                    current_committee_type = 'program'
                    current_position = 'chair'
                    # Extract the chair from this same paragraph
                    text = p.get_text()
                    if ':' in text:
                        chair_info = text.split(':', 1)[1].strip()
                        member = self._parse_member_text(chair_info, current_committee_type, current_position)
                        if member:
                            members.append(member)
                    continue
                
                elif 'topic chair' in header_text or 'area chair' in header_text:
                    current_committee_type = 'program'
                    current_position = 'area_chair'
                    continue
                
                elif 'technical operations chair' in header_text:
                    current_committee_type = 'program'
                    current_position = 'chair'
                    # Extract the chair from this same paragraph
                    text = p.get_text()
                    if ':' in text:
                        chair_info = text.split(':', 1)[1].strip()
                        member = self._parse_member_text(chair_info, current_committee_type, current_position)
                        if member:
                            members.append(member)
                    continue
                
                elif 'full program committee' in header_text or 'programme committee' in header_text:
                    current_committee_type = 'program'
                    current_position = 'member'
                    continue
                
                elif 'steering committee' in header_text:
                    current_committee_type = 'steering'
                    current_position = 'member'
                    continue
                
                elif 'organizing' in header_text or 'local' in header_text:
                    current_committee_type = 'local_organizing'
                    current_position = 'member'
                    continue
            
            # Skip if we don't know what committee this is
            if not current_committee_type:
                continue
            
            # Parse members from <br> separated list
            # Check if this paragraph contains <br> tags
            if p.find('br'):
                # Get HTML content and split by <br>
                html = str(p)
                # Split by <br> or <br/>
                import re
                parts = re.split(r'<br\s*/?>', html)
                
                for part in parts:
                    # Remove HTML tags
                    from bs4 import BeautifulSoup
                    clean_text = BeautifulSoup(part, 'html.parser').get_text(strip=True)
                    
                    if clean_text and len(clean_text) > 3:
                        member = self._parse_member_text(clean_text, current_committee_type, current_position)
                        if member:
                            members.append(member)
        
        return members
    
    def _parse_member_text(self, text: str, committee_type: str, position: str) -> Dict[str, str]:
        """Parse a member from text like 'Name, Affiliation' or 'Role: Name, Affiliation'."""
        text = text.strip()
        if not text or len(text) < 3:
            return None
        
        # Remove common artifacts
        text = text.replace('&nbsp;', ' ').strip()
        
        # Check if it's a role line (e.g., "Quantum algorithms: Name, Affiliation")
        if ':' in text and any(keyword in text.lower() for keyword in ['quantum', 'cryptography', 'complexity', 'theory', 'tomography', 'learning', 'error correction', 'foundations']):
            # This is a topic chair line
            parts = text.split(':', 1)
            if len(parts) == 2:
                text = parts[1].strip()
                position = 'area_chair'
        
        # Split by comma to get name and affiliation
        if ',' in text:
            parts = text.rsplit(',', 1)
            name = self.normalize_name(parts[0].strip())
            affiliation = self.normalize_affiliation(parts[1].strip()) if len(parts) > 1 else None
        else:
            # No comma, treat entire text as name
            name = self.normalize_name(text)
            affiliation = None
        
        if not name:
            return None
        
        return {
            'committee_type': committee_type,
            'position': position,
            'full_name': name,
            'affiliation': affiliation,
            'notes': None
        }
