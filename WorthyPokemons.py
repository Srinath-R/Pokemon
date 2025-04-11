import requests
import pandas as pd
from tqdm import tqdm
import time
import json
import os
import argparse

# Pickle data to avoid repeated API calls
def save_dictionary(data, filename):
    with open(filename, 'w') as file:
        json.dump(data, file)

def load_dictionary(filename):
    if os.path.exists(filename):
        with open(filename, 'r') as file:
            return json.load(file)
    return None

# Cache file paths
TYPE_CHART_FILENAME = 'type_chart.json'
POKEMON_DETAILS_CACHE = 'pokemon_details.json'
SPECIES_INFO_CACHE = 'species_info.json'

def get_all_pokemon(limit=1025):
    """Get a list of all Pokémon with their URLs."""
    url = f"https://pokeapi.co/api/v2/pokemon?limit={limit}"
    response = requests.get(url)
    return response.json()['results']

def get_pokemon_details(url, details_cache, max_retries=3, retry_delay=1):
    """Get detailed information for a specific Pokémon with caching and retry mechanism."""
    # Check if this URL is in our cache
    if url in details_cache:
        return details_cache[url]
        
    for attempt in range(max_retries):
        try:
            response = requests.get(url)
            if response.status_code == 200:
                pokemon_data = response.json()
                # Store in cache
                details_cache[url] = pokemon_data
                return pokemon_data
            elif response.status_code == 429:  # Rate limit exceeded
                retry_after = int(response.headers.get('Retry-After', retry_delay * 2))
                print(f"Rate limit hit. Waiting for {retry_after} seconds...")
                time.sleep(retry_after)
            else:
                time.sleep(retry_delay)
        except (json.JSONDecodeError, requests.RequestException) as e:
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                raise Exception(f"Failed to get data after {max_retries} attempts: {str(e)}")
    return None

def get_species_info(pokemon_id, species_cache, max_retries=3, retry_delay=1):
    """Get species information with caching and retry mechanism."""
    # Check if this ID is in our cache
    if pokemon_id in species_cache:
        return species_cache[pokemon_id]
    
    url = f"https://pokeapi.co/api/v2/pokemon-species/{pokemon_id}/"
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url)
            if response.status_code == 200:
                species_data = response.json()
                # Store in cache
                species_cache[pokemon_id] = species_data
                return species_data
            elif response.status_code == 404:
                # Some special forms don't have their own species entry
                # In this case, try to get the base form's ID
                base_id = str(pokemon_id).split('-')[0]
                if base_id.isdigit():
                    url = f"https://pokeapi.co/api/v2/pokemon-species/{base_id}/"
                    continue
                else:
                    default_data = {"is_legendary": False, "is_mythical": False}
                    species_cache[pokemon_id] = default_data
                    return default_data
            elif response.status_code == 429:  # Rate limit exceeded
                retry_after = int(response.headers.get('Retry-After', retry_delay * 2))
                print(f"Rate limit hit. Waiting for {retry_after} seconds...")
                time.sleep(retry_after)
            else:
                time.sleep(retry_delay)
        except (json.JSONDecodeError, requests.RequestException) as e:
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                raise Exception(f"Failed to get species data after {max_retries} attempts: {str(e)}")
    
    default_data = {"is_legendary": False, "is_mythical": False}
    species_cache[pokemon_id] = default_data
    return default_data  # Default if all attempts fail

def get_type_effectiveness(type_name):
    """Get damage relationships for a specific type."""
    url = f"https://pokeapi.co/api/v2/type/{type_name}/"
    response = requests.get(url)
    return response.json()['damage_relations']

def calculate_defensive_effectiveness(pokemon_types, type_chart):
    """Calculate how many types a Pokémon resists or is immune to."""
    immunities = set()
    quarter_damage = set()
    half_damage = set()
    
    for poke_type in pokemon_types:
        relations = type_chart[poke_type]
        
        # No damage (immunities)
        for immunity in relations['no_damage_from']:
            # Extract the type name instead of using the whole dict
            immunity_type = immunity['name']
            immunities.add(immunity_type)
        
        # Half damage
        for resistance in relations['half_damage_from']:
            # Extract the type name
            resistance_type = resistance['name']
            if resistance_type in immunities:
                continue
            elif resistance_type in quarter_damage:
                continue
            elif resistance_type in half_damage:
                quarter_damage.add(resistance_type)
                half_damage.remove(resistance_type)
            else:
                half_damage.add(resistance_type)
    
    return len(immunities) + len(quarter_damage) + len(half_damage)

def is_special_form(pokemon_name):
    """Check if a Pokémon is a special form (mega, regional, etc.)."""
    # Forms that contain a hyphen but aren't considered "alternate" forms
    exceptions = ['kommo-o', 'hakamo-o', 'jangmo-o', 'type-null', 'ho-oh', 'porygon-z']
    if '-' in pokemon_name and pokemon_name not in exceptions:
        return True
    return False

def is_gmax_or_gender_form(pokemon_name):
    """Check if form is Gigantamax or gender-specific variant."""
    gmax_indicators = ['gmax-', 'gigantamax-']
    gender_indicators = ['-male', '-female']
    
    for indicator in gmax_indicators + gender_indicators:
        if indicator in pokemon_name.lower():
            return True
    return False

def format_pokemon_name(pokemon_name):
    """Format Pokémon names with special forms to be more readable."""
    exceptions = ['kommo-o', 'hakamo-o', 'jangmo-o', 'type-null', 'ho-oh', 'porygon-z']
    if pokemon_name.lower() in exceptions:
        return pokemon_name.title()
        
    if '-' not in pokemon_name:
        return pokemon_name.title()
    
    parts = pokemon_name.split('-')
    base_name = parts[0].title()
    form_name = '-'.join(parts[1:])
    
    # Standard form prefixes that should go before the name
    prefix_forms = {
        'mega': 'Mega',
        'alolan': 'Alolan',
        'galarian': 'Galarian',
        'hisuian': 'Hisuian',
        'paldean': 'Paldean',
        'primal': 'Primal'
    }
    
    # Check if it's a prefix form
    if form_name.lower() in prefix_forms:
        return f"{prefix_forms[form_name.lower()]} {base_name}"
    
    # Special case for Mega X/Y forms
    if form_name.lower().startswith('mega'):
        if len(parts) > 2:  # Has X/Y suffix
            return f"Mega {base_name} {parts[-1].upper()}"
        return f"Mega {base_name}"
    
    # For all other forms, use parentheses
    return f"{base_name} ({form_name.title()})"

def is_excluded_pokemon(pokemon_name):
    """Check if a Pokémon should be excluded (Ultra Beast, Paradox, etc.)."""
    # Ultra Beasts to exclude
    ultra_beasts = [
        'nihilego', 'buzzwole', 'pheromosa', 'xurkitree', 'celesteela',
        'kartana', 'guzzlord', 'poipole', 'naganadel', 'stakataka', 'blacephalon'
    ]
    
    # Paradox Pokémon to exclude
    paradox_pokemon = [
        'great-tusk', 'scream-tail', 'brute-bonnet', 'flutter-mane', 'slither-wing',
        'sandy-shocks', 'iron-treads', 'iron-bundle', 'iron-hands', 'iron-jugulis',
        'iron-moth', 'iron-thorns', 'iron-valiant', 'roaring-moon', 'iron-leaves',
        'walking-wake', 'gouging-fire', 'raging-bolt', 'iron-boulder', 'iron-crown'
    ]
    
    return pokemon_name in ultra_beasts or pokemon_name in paradox_pokemon

def get_base_form_name(pokemon_name):
    """Extract the base form name from a Pokémon name."""
    # List of words that indicate it's a form name
    form_indicators = ['mega', 'alolan', 'galarian', 'hisuian', 'paldean', 
                      'primal', 'eternamax', 'gmax', 'gigantamax']
    
    # Split by hyphen and get the first part
    base_name = pokemon_name.split('-')[0]
    
    # If the first part is a form indicator, the second part is the base name
    if base_name.lower() in form_indicators and len(pokemon_name.split('-')) > 1:
        base_name = pokemon_name.split('-')[1]
    
    return base_name

def get_pokemon_signature(pokemon_data):
    """Create a unique signature for a Pokémon based on its stats and types."""
    types = sorted([t['type']['name'] for t in pokemon_data['types']])
    stats = [stat['base_stat'] for stat in pokemon_data['stats']]
    return (tuple(types), tuple(stats))

def is_legendary_or_mythical(pokemon_name, pokemon_id, species_cache, pokemon_details_cache):
    """Check if a Pokémon or its base form is legendary/mythical."""
    try:
        # First try with current ID
        species_data = get_species_info(pokemon_id, species_cache)
        if species_data['is_legendary'] or species_data['is_mythical']:
            return True
        
        # If it's a form, check the base form
        if is_special_form(pokemon_name):
            base_name = get_base_form_name(pokemon_name)
            base_url = f"https://pokeapi.co/api/v2/pokemon/{base_name}/"
            base_data = get_pokemon_details(base_url, pokemon_details_cache)
            if base_data:
                species_data = get_species_info(base_data['id'], species_cache)
                return species_data['is_legendary'] or species_data['is_mythical']
    except Exception:
        # If we can't determine, better to exclude it
        return True
    return False

def get_national_dex_number(pokemon_name, pokemon_id, species_cache, pokemon_details_cache):
    """Get the National Pokédex number for a Pokémon."""
    try:
        # Get species info for the current Pokémon
        species_data = get_species_info(pokemon_id, species_cache)
        if 'id' in species_data:
            return species_data['id']
    except Exception:
        # If we can't get the proper number, return the API ID as fallback
        return pokemon_id
    return pokemon_id

def main():
    # Set up command line arguments
    parser = argparse.ArgumentParser(description='Analyze Pokémon based on stats and type advantages')
    parser.add_argument('--include-forms', action='store_true', help='Include mega evolutions, regional forms, and other variants')
    parser.add_argument('--min-bst', type=int, default=525, help='Minimum base stat total (default: 525)')
    parser.add_argument('--refresh-cache', action='store_true', help='Ignore cached data and refresh from API')
    args = parser.parse_args()
    
    print("Fetching Pokémon data...")

    # Load cached data or create new caches if needed
    if args.refresh_cache:
        type_chart = None
        pokemon_details_cache = {}
        species_info_cache = {}
        print("Cache refresh requested. All data will be fetched from API.")
    else:
        type_chart = load_dictionary(TYPE_CHART_FILENAME)
        pokemon_details_cache = load_dictionary(POKEMON_DETAILS_CACHE) or {}
        species_info_cache = load_dictionary(SPECIES_INFO_CACHE) or {}
        print(f"Loaded {len(pokemon_details_cache)} Pokémon details and {len(species_info_cache)} species from cache.")
    
    # First, build a type effectiveness chart if not present
    if type_chart is None:
        print("Type effectiveness chart not found.")
        type_chart = {}
        all_types = requests.get("https://pokeapi.co/api/v2/type").json()['results']
        print("Building type effectiveness chart...")
        for type_info in tqdm(all_types):
            if type_info['name'] in ['unknown', 'shadow']:  # Skip non-battle types
                continue
            type_chart[type_info['name']] = get_type_effectiveness(type_info['name'])
            time.sleep(0.1)  # Avoid hitting rate limits
        save_dictionary(type_chart, TYPE_CHART_FILENAME)
        print("Type effectiveness chart built and saved.")
    else:
        print("Loaded existing type effectiveness chart.")
    
    # Get all Pokémon - use a higher limit to make sure we get all of them
    all_pokemon = []

    # Get all Pokémon and forms in a single call
    all_pokemon = get_all_pokemon(limit=4000)  # This will cover all base Pokémon and forms
    
    # Filter forms based on criteria
    filtered_pokemon = []
    for pokemon in all_pokemon:
        if is_gmax_or_gender_form(pokemon['name']):
            # Always exclude Gmax and gender variants
            continue
        elif not is_special_form(pokemon['name']):
            # Always include base forms
            filtered_pokemon.append(pokemon)
        elif args.include_forms:
            # Include other special forms (mega, regional, etc.) when --include-forms is used
            filtered_pokemon.append(pokemon)
    
    all_pokemon = filtered_pokemon

    print(f"Analyzing {len(all_pokemon)} Pokémons...")
    results = []
    error_count = 0
    processed_signatures = {}  # Track unique Pokémon signatures
    
    for pokemon in tqdm(all_pokemon):
        try:
            # Skip Paradox Pokémon and Ultra Beasts before making API calls
            if is_excluded_pokemon(pokemon['name']):
                continue
            
            # Get basic details
            pokemon_data = get_pokemon_details(pokemon['url'], pokemon_details_cache)
            if pokemon_data is None:
                continue
            
            pokemon_id = pokemon_data['id']
            national_dex_no = get_national_dex_number(pokemon_data['name'], pokemon_id, species_info_cache, pokemon_details_cache)
            
            # Check if legendary/mythical (including base form check)
            if is_legendary_or_mythical(pokemon_data['name'], pokemon_id, species_info_cache, pokemon_details_cache):
                continue
            
            # Calculate base stats total
            stats_total = sum(stat['base_stat'] for stat in pokemon_data['stats'])
            if stats_total < args.min_bst:
                continue
            
            # Get Pokémon signature
            pokemon_signature = get_pokemon_signature(pokemon_data)
            base_name = get_base_form_name(pokemon_data['name'])
            
            # Skip if this is an alternate form with the same signature as its base form
            if base_name != pokemon_data['name']:
                try:
                    base_url = f"https://pokeapi.co/api/v2/pokemon/{base_name}/"
                    base_data = get_pokemon_details(base_url, pokemon_details_cache)
                    base_signature = get_pokemon_signature(base_data)
                    if base_signature == pokemon_signature:
                        continue
                except:
                    pass  # If we can't get base form data, treat this as a unique form
            
            # Skip duplicates based on signature
            signature_key = (base_name, pokemon_signature)
            if signature_key in processed_signatures:
                continue
            processed_signatures[signature_key] = True
            
            # Get Pokémon types
            pokemon_types = [t['type']['name'] for t in pokemon_data['types']]
            
            # Calculate defensive advantages
            defensive_score = calculate_defensive_effectiveness(pokemon_types, type_chart)
            
            results.append({
                'name': format_pokemon_name(pokemon_data['name']),
                'id': national_dex_no,  # Use National Dex number instead of API ID
                'types': ', '.join(t.title() for t in pokemon_types),
                'base_stats_total': stats_total,
                'defensive_advantages': defensive_score
            })
            
            if len(results) % 20 == 0:
                time.sleep(0.5)
            
        except Exception as e:
            error_count += 1
            print(f"Error processing {pokemon['name']}: {str(e)}")
    
    # Save caches for future use
    save_dictionary(pokemon_details_cache, POKEMON_DETAILS_CACHE)
    save_dictionary(species_info_cache, SPECIES_INFO_CACHE)
    print(f"Saved {len(pokemon_details_cache)} Pokémon details and {len(species_info_cache)} species info to cache")
    
    if error_count > 0:
        print(f"\nTotal errors encountered: {error_count}")
        
    if not results:
        print("No Pokémon matched the criteria!")
        return
        
    # Convert to DataFrame and sort by our criteria
    df = pd.DataFrame(results)
    
    # Sort by defensive effectiveness score, then by base stats
    df = df.sort_values(by=['defensive_advantages', 'base_stats_total'], ascending=False)
    
    # Display top results
    print(f"\nTop Non-Legendary Pokémon (Base Stats ≥ {args.min_bst}) sorted by Type Advantages:")
    pd.set_option('display.max_rows', None)
    pd.set_option('display.width', 1000)
    print(df[['name', 'id', 'types', 'base_stats_total', 'defensive_advantages']])
    
    # Save results to CSV
    forms_text = "_with_forms" if args.include_forms else ""
    csv_filename = f'pokemon_analysis{forms_text}.csv'
    df.to_csv(csv_filename, index=False)
    print(f"\nResults saved to '{csv_filename}'")

if __name__ == "__main__":
    main()