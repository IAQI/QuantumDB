"""QCrypt conference committee scraper."""
import re
from typing import List, Dict, Optional
from .base import BaseCommitteeScraper


class QCryptScraper(BaseCommitteeScraper):
    """Scraper for QCrypt conference committee pages."""
    
    def get_url(self) -> str:
        """Return the URL for QCrypt committee page."""
        if self.year >= 2020:
            return f"https://2023.qcrypt.net/committees/"  # Most recent format
        elif self.year >= 2016:
            return f"https://{self.year}.qcrypt.net/committees/"
        else:
            # Older format, might need customization
            return f"https://www.qcrypt.net/{self.year}/committees.html"
    
    def parse_committee_data(self) -> List[Dict[str, str]]:
        """Parse committee data from QCrypt HTML.
        
        QCrypt typically uses <section class="members"> with <ul class="members">
        containing structured <li> elements with name, affiliation, and role.
        Older sites (pre-2020) may use <p><em> tags for headings.
        """
        members = []
        
        # Find all committee sections (both h2/h3/h4 and p>em format)
        sections = self.soup.find_all(['h2', 'h3', 'h4'])
        
        # Also check for older formats:
        # 1. <p><em><span>Committee Name</span></em></p>
        # 2. <p><strong>Committee Name</strong></p>
        # Look for both "committee" and "organizer" keywords
        for p in self.soup.find_all('p'):
            # Check for <em> tag
            em = p.find('em')
            if em:
                em_text = em.get_text().lower()
                if 'committee' in em_text or 'organizer' in em_text or 'organiser' in em_text:
                    sections.append(p)
                    continue
            
            # Check for <strong> tag
            strong = p.find('strong')
            if strong:
                strong_text = strong.get_text().lower()
                if 'committee' in strong_text or 'organizer' in strong_text or 'organiser' in strong_text:
                    sections.append(p)
        
        for section_heading in sections:
            heading_text = section_heading.get_text().lower()
            
            # Determine committee type
            committee_type = None
            if 'program committee' in heading_text or 'programme committee' in heading_text or 'pc members' in heading_text:
                committee_type = 'program'
            elif 'steering committee' in heading_text:
                committee_type = 'steering'
            elif 'organizing committee' in heading_text or 'local' in heading_text or 'oc support' in heading_text:
                committee_type = 'local_organizing'
            elif 'advisory committee' in heading_text:
                committee_type = 'steering'  # Treat advisory as steering
            
            if not committee_type:
                continue
            
            # Find the members section following this heading
            current = section_heading
            is_legacy_format = section_heading.name == 'p'
            heading_level = section_heading.name if section_heading.name in ['h2', 'h3', 'h4'] else None
            
            while current:
                current = current.next_sibling
                
                # Skip text nodes
                if not hasattr(current, 'name') or current.name is None:
                    continue
                
                # Stop at next heading of same or higher level
                if heading_level and current.name in ['h2', 'h3', 'h4']:
                    # Stop if we hit h2 (always higher level)
                    if current.name == 'h2':
                        break
                    # For h3 and h4, stop if same or higher level
                    if heading_level == 'h3' and current.name in ['h3']:
                        break
                    if heading_level == 'h4' and current.name in ['h3', 'h4']:
                        break
                
                # For legacy format, stop at next committee paragraph
                if is_legacy_format and current.name == 'p':
                    em = current.find('em')
                    strong = current.find('strong')
                    if (em and 'committee' in em.get_text().lower()) or \
                       (strong and 'committee' in strong.get_text().lower()):
                        break
                    
                    # Check if this is a paragraph with <br> separated names (2011 format)
                    # It should have class="p" and contain <br> tags
                    if current.get('class') == ['p'] and current.find('br'):
                        members.extend(self._parse_br_separated_list(current, committee_type, heading_text))
                        continue
                
                # Look for section.members or direct ul
                member_section = None
                if current.name == 'section' and 'members' in current.get('class', []):
                    member_section = current
                elif hasattr(current, 'find'):
                    member_section = current.find('section', class_='members', recursive=False)
                
                if member_section:
                    members.extend(self._parse_member_section(member_section, committee_type, heading_text))
                    # Don't break - continue looking for subsections
                elif current.name == 'ul':
                    # Plain list format
                    members.extend(self._parse_plain_list(current, committee_type, heading_text))
                    # Don't break - continue looking for more lists
        
        return members
    
    def _parse_member_section(self, section, committee_type: str, heading_text: str) -> List[Dict[str, str]]:
        """Parse a <section class="members"> element."""
        members = []
        member_list = section.find('ul', class_='members')
        
        if not member_list:
            return members
        
        for li in member_list.find_all('li', recursive=False):
            member = self._parse_member_li(li, committee_type, heading_text)
            if member:
                members.append(member)
        
        return members
    
    def _parse_member_li(self, li, committee_type: str, heading_text: str) -> Optional[Dict[str, str]]:
        """Parse a member <li> element with structured data."""
        label = li.find('div', class_='label')
        
        if not label:
            # Fallback to plain text
            text = li.get_text(' ', strip=True)
            return self._parse_plain_text(text, committee_type, heading_text)
        
        # Extract name from h3
        h3 = label.find('h3')
        if not h3:
            return None
        
        name = self.normalize_name(h3.get_text(strip=True))
        
        # Extract affiliation and role from h4 tags
        h4_tags = label.find_all('h4')
        affiliation = None
        role_text = ''
        
        for h4 in h4_tags:
            h4_text = h4.get_text(strip=True)
            # Role indicators
            if any(kw in h4_text.lower() for kw in ['chair', 'member', 'co-chair', 'area chair']):
                role_text = h4_text
            elif not affiliation:
                affiliation = self.normalize_affiliation(h4_text)
        
        # Detect position from role text and heading
        position = self._detect_position(name, role_text, heading_text)
        
        # Detect specialized role title
        role_title = self.detect_role_title(role_text, heading_text)
        
        return {
            'committee_type': committee_type,
            'position': position,
            'full_name': name,
            'affiliation': affiliation,
            'role_title': role_title
        }
    
    def _parse_plain_list(self, ul, committee_type: str, heading_text: str) -> List[Dict[str, str]]:
        """Parse a plain <ul> list of members."""
        members = []
        
        for li in ul.find_all('li', recursive=False):
            # Check if there are anchor tags (newer format with links)
            anchors = li.find_all('a')
            
            if anchors:
                # Extract name from first non-mailto link
                name = None
                for a in anchors:
                    href = a.get('href', '')
                    if not href.startswith('mailto:'):
                        name = a.get_text(strip=True)
                        break
                
                if not name:
                    # If all links are mailto, skip this entry
                    continue
                
                # Get text from the li element, then remove anchor text manually
                full_text = li.get_text(' ', strip=True)
                
                # Remove all anchor texts from the full text
                for a in anchors:
                    anchor_text = a.get_text(strip=True)
                    full_text = full_text.replace(anchor_text, '')
                
                remaining_text = full_text
                affiliation = None
                
                # Extract affiliation from parentheses or brackets in the name itself
                paren_match = re.search(r'[\(\[]([^\)\]]+)[\)\]]', name)
                if paren_match:
                    affiliation = self.normalize_affiliation(paren_match.group(1))
                    name = re.sub(r'\s*[\(\[]([^\)\]]+)[\)\]]\s*', '', name)
                
                # Also check remaining text for affiliation in parentheses/brackets
                if not affiliation:
                    # Remove email-like patterns
                    remaining_text = re.sub(r'\S+@\S+', '', remaining_text)
                    remaining_text = remaining_text.strip()
                    if remaining_text:
                        # Check for parentheses/brackets pattern for affiliation
                        match = re.match(r'[\(\[]([^\)\]]+)[\)\]]', remaining_text)
                        if match:
                            affiliation = self.normalize_affiliation(match.group(1))
                
                # Normalize the name after extraction
                name = self.normalize_name(name)
                
                # Check if there's a chair designation after the dash
                position = 'member'
                # Only match dashes with whitespace before them (not hyphens in names)
                dash_match = re.search(r'\s+[–—-]\s*(.+)$', remaining_text)
                if dash_match:
                    role_text = dash_match.group(1).strip().lower()
                    # Check for chair designation
                    if 'co-chair' in role_text or 'co chair' in role_text:
                        position = 'co-chair'
                    elif 'chair' in role_text:
                        position = 'chair'
                
                # Override position detection if we didn't find chair in text
                if position == 'member':
                    position = self._detect_position(name, heading_text, heading_text)
                
                # Detect specialized role title
                role_title = self.detect_role_title(remaining_text, heading_text)
                
                members.append({
                    'committee_type': committee_type,
                    'position': position,
                    'full_name': name,
                    'affiliation': affiliation,
                    'role_title': role_title
                })
            else:
                # Fallback to plain text parsing
                text = li.get_text(' ', strip=True)
                member = self._parse_plain_text(text, committee_type, heading_text)
                if member:
                    members.append(member)
        
        return members
    
    def _parse_br_separated_list(self, p_tag, committee_type: str, heading_text: str) -> List[Dict[str, str]]:
        """Parse a <p> tag with <br> separated member names (2011 format).
        
        Example: <p>Name1<br />Name2 (chair)<br />Name3</p>
        """
        members = []
        
        # Get the HTML content and split by <br> tags
        # Replace <br> and <br/> tags with a delimiter
        import re
        html_content = str(p_tag)
        # Split by <br> tags (various formats: <br>, <br/>, <br />)
        parts = re.split(r'<br\s*/?>', html_content)
        
        for part in parts:
            # Remove HTML tags and get clean text
            from bs4 import BeautifulSoup
            clean_text = BeautifulSoup(part, 'html.parser').get_text(strip=True)
            
            if clean_text and len(clean_text) > 2:
                member = self._parse_plain_text(clean_text, committee_type, heading_text)
                if member:
                    members.append(member)
        
        return members
    
    def _parse_plain_text(self, text: str, committee_type: str, heading_text: str) -> Optional[Dict[str, str]]:
        """Parse member info from plain text."""
        if len(text) < 3 or len(text) > 300:
            return None
        
        # Skip navigation/header items
        text_lower = text.lower()
        blacklist = ['twitter', 'youtube', 'linkedin', 'steering committee', 
                     'program committee', 'organizing committee']
        if any(item in text_lower for item in blacklist) and len(text) < 100:
            return None
        
        # Check for chair designation in job description before removing it
        position = 'member'
        # Only match dashes with whitespace before them (not hyphens in names like Sheng-Kai)
        dash_match = re.search(r'\s+[–—-]\s*(.+)$', text)
        if dash_match:
            role_text = dash_match.group(1).strip().lower()
            if 'co-chair' in role_text or 'co chair' in role_text:
                position = 'co-chair'
            elif 'chair' in role_text:
                position = 'chair'
            # Remove job description after dash
            text = re.sub(r'\s+[–—-]\s*.+$', '', text)
        
        # Try to parse "Name (Affiliation)" or "Name [Affiliation]" or "Name, Affiliation" patterns
        name = text
        affiliation = None
        
        # Pattern: Name (Affiliation) or Name [Affiliation]
        match = re.match(r'^(.+?)\s*[\(\[]([^\)\]]+)[\)\]]\s*(.*)$', text)
        if match:
            name = self.normalize_name(match.group(1))
            paren_content = match.group(2)
            paren_lower = paren_content.lower()
            
            # Check if parentheses contain position/role information rather than affiliation
            position_indicators = ['chair', 'co-chair', 'co chair']
            is_position_info = any(indicator in paren_lower for indicator in position_indicators)
            
            # For local organizing committees, check for broader role descriptions
            role_keywords = ['webmaster', 'web', 'poster', 'session', 'dinner', 'coordinator',
                           'package', 'rump', 'support', 'visa', 'registration', 'industry',
                           'student', 'general chair', 'lead', 'video', 'slides',
                           'magic', 'contact', 'welcome']
            
            if committee_type == 'local_organizing' and any(kw in paren_lower for kw in role_keywords):
                # This is role information, not affiliation
                affiliation = None
                # Check for chair/lead positions
                if 'general chair' in paren_lower or 'lead' in paren_lower or 'coordinator' in paren_lower:
                    position = 'chair'
                elif 'co-chair' in paren_lower or 'co chair' in paren_lower:
                    position = 'co-chair'
            elif is_position_info:
                # For any committee, if it's clearly a position (chair, co-chair), don't treat as affiliation
                affiliation = None
                if 'co-chair' in paren_lower or 'co chair' in paren_lower:
                    position = 'co-chair'
                elif 'chair' in paren_lower:
                    position = 'chair'
            else:
                # This is affiliation information
                affiliation = self.normalize_affiliation(paren_content)
            
            # Check if there's additional text in parentheses for position info
            remaining = match.group(3).strip()
            if remaining and position == 'member':
                # Look for position indicators like (lead organizer), (chair), etc.
                extra_match = re.match(r'[\(\[]([^\)\]]+)[\)\]]', remaining)
                if extra_match:
                    role_text = extra_match.group(1).lower()
                    if 'lead' in role_text or 'chair' in role_text:
                        position = 'chair'
                    elif 'co-chair' in role_text or 'co chair' in role_text:
                        position = 'co-chair'
        else:
            # Pattern: Name, Affiliation
            parts = text.split(',', 1)
            if len(parts) == 2:
                name = self.normalize_name(parts[0])
                affiliation = self.normalize_affiliation(parts[1])
            else:
                name = self.normalize_name(text)
        
        # Override if not already chair
        if position == 'member':
            position = self._detect_position(name, text, heading_text)
        
        # Detect specialized role title
        role_title = self.detect_role_title(text, heading_text)
        
        return {
            'committee_type': committee_type,
            'position': position,
            'full_name': name,
            'affiliation': affiliation,
            'role_title': role_title
        }
    
    def _detect_position(self, name: str, role_text: str, heading_text: str) -> str:
        """Detect the position/role of a committee member."""
        combined = f"{heading_text} {role_text}".lower()
        
        if 'co-chair' in combined or 'co chair' in combined:
            return 'co-chair'
        elif 'chair' in combined:
            return 'chair'
        else:
            return 'member'
