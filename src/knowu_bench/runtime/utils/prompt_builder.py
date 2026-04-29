import json

class PersonaPromptBuilder:
    def __init__(self, user_profile: dict):
        self.profile = user_profile
        self.identity = self.profile.get('identity', {})

    def build_system_prompt(self) -> str:
        prompt = [
            f"You are {self.identity.get('full_name', 'User')}.",
            f"You are a {self.identity.get('age')} year old {self.identity.get('occupation')} working at {self.identity.get('employer')}.",
            "Your goal is to simulate this user's behavior realistically on a mobile device."
        ]
        
        exclude_keys = {'full_name', 'age', 'occupation', 'employer'}
        
        if 'contact_info' in self.identity:
            prompt.append("\n[Contact Details]")
            for k, v in self.identity['contact_info'].items():
                prompt.append(f"- {k.replace('_', ' ').title()}: {v}")
            exclude_keys.add('contact_info')

        if 'auth_documents' in self.identity:
            prompt.append("\n[Documents]")
            for k, v in self.identity['auth_documents'].items():
                prompt.append(f"- {k.replace('_', ' ').title()}: {v}")
            exclude_keys.add('auth_documents')

        other_identity = {k: v for k, v in self.identity.items() if k not in exclude_keys}
        if other_identity:
            prompt.append("\n[Other Identity Traits]")
            for k, v in other_identity.items():
                prompt.append(f"- {k.replace('_', ' ').title()}: {v}")

        prompt.append("")

        locations = self.profile.get('locations', {})
        if locations:
            prompt.append("### PHYSICAL LOCATIONS")
            for key, val in locations.items():
                if isinstance(val, dict):
                    address = val.get('address', 'Unknown')
                    instr = f" (Instruction: {val.get('instructions')})" if val.get('instructions') else ""
                    prompt.append(f"- {key.capitalize()}: {address}{instr}")
                else:
                    prompt.append(f"- {key.capitalize()}: {val}")
            prompt.append("")

        digital = self.profile.get('digital_context', {})
        if digital:
            prompt.append("### DIGITAL CONTEXT")
            for category, details in digital.items():
                prompt.append(f"- {category.replace('_', ' ').title()}: {json.dumps(details, ensure_ascii=False)}")
            prompt.append("")

        habits = self.profile.get('habits', {})
        if habits:
            prompt.append("### BEHAVIORAL HABITS")
            for category, details in habits.items():
                label = category.replace('_', ' ').title()
                prompt.append(f"- {label}: {json.dumps(details, ensure_ascii=False)}")
            prompt.append("")

        preferences = self.profile.get('preferences', {})
        if preferences:
            prompt.append("### PREFERENCES & LIFESTYLE")
            for category, details in preferences.items():
                prompt.append(f"- {category.replace('_', ' ').title()}: {json.dumps(details, ensure_ascii=False)}")
            prompt.append("")

        social = self.profile.get('social_graph', {})
        if social:
            prompt.append("### SOCIAL GRAPH")
            for group_key, people in social.items():
                group_name = group_key.replace('_', ' ').title()
                prompt.append(f"[{group_name} Contacts]:")
                
                if isinstance(people, list):
                    for person in people:
                        if isinstance(person, dict):
                            name = person.get('name', 'Unknown')
                            role = person.get('role', 'N/A')
                            strategy = person.get('instruction', 'N/A')
                            person_str = f"  - Name: {name} | Role: {role} | Strategy: {strategy}"
                            
                            extras = {k: v for k, v in person.items() if k not in ['name', 'role', 'instruction']}
                            if extras:
                                person_str += f" | Info: {json.dumps(extras, ensure_ascii=False)}"
                            prompt.append(person_str)
                        else:
                            prompt.append(f"  - {person}")
            prompt.append("")

        criteria = self.profile.get('decision_criteria', {})
        if criteria:
            prompt.append("### DECISION MAKING LOGIC")
            prompt.append("When faced with choices, strictly adhere to the following values:")
            
            for criterion_type, items in criteria.items():
                label = criterion_type.replace('_', ' ').title()
                if isinstance(items, list):
                    items_str = ", ".join([str(i) for i in items])
                    prompt.append(f"- {label}: {items_str}")
                else:
                    prompt.append(f"- {label}: {json.dumps(items, ensure_ascii=False)}")
            prompt.append("")

        known_keys = {
            'identity', 'locations', 'digital_context', 
            'habits', 'preferences', 'social_graph', 'decision_criteria'
        }
        unknown_sections = {k: v for k, v in self.profile.items() if k not in known_keys}
        
        if unknown_sections:
            prompt.append("### ADDITIONAL INFORMATION")
            for k, v in unknown_sections.items():
                prompt.append(f"- {k.replace('_', ' ').title()}: {json.dumps(v, ensure_ascii=False)}")
            prompt.append("")

        prompt.append("### CURRENT SITUATION")
        prompt.append("You have just unlocked your phone. Review your environment state (unread messages, calendar events, active notifications) and proceed based on your identity and habits.")
        
        return "\n".join(prompt)