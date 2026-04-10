import csv
import re
from collections import defaultdict

def calculate_crossword_weight(score):
    """
    Treats the logarithmic score linearly to flatten the distribution,
    which better approximates crossword utility. Adds 1 so score=0 
    words still register a baseline frequency.
    """
    return score + 1

def process_wordlist_for_crosswords(file_path):
    bigram_counts = defaultdict(float)
    
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        reader = csv.reader(f)
        
        for row in reader:
            if len(row) != 2:
                continue
                
            raw_word, score_str = row[0], row[1]
            
            try:
                score = float(score_str)
            except ValueError:
                continue
                
            # Sanitise: Lowercase and strip non-alpha characters
            clean_word = re.sub(r'[^a-z]', '', raw_word.lower())
            
            # Apply the flattened crossword weighting
            weight = calculate_crossword_weight(score)
            
            # Extract bigrams
            if len(clean_word) >= 2:
                for i in range(len(clean_word) - 1):
                    bigram = clean_word[i:i+2]
                    bigram_counts[bigram] += weight
                    
    # Sort the dictionary by weight in descending order
    sorted_bigrams = sorted(bigram_counts.items(), key=lambda item: item[1], reverse=True)
    
    return sorted_bigrams

def export_filtered_bigrams(bigrams, output_file, threshold):
    """
    Writes bigrams exceeding the threshold to a CSV file.
    """
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Bigram', 'Weight']) # Add a header row
        
        count = 0
        for bigram, weight in bigrams:
            if weight > threshold:
                writer.writerow([bigram.upper(), round(weight, 2)])
                count += 1
            else:
                # Since the list is sorted, once we drop below the threshold, 
                # we can safely stop checking the rest to save processing time.
                break 
                
    return count

# --- Execution Block ---
input_file = 'OED - CC.csv'
output_file = 'top_crossword_bigrams.csv'
minimum_weight = -1

print(f"Analyzing '{input_file}'...")
results = process_wordlist_for_crosswords(input_file)

print(f"Exporting pairs with weight > {minimum_weight}...")
saved_count = export_filtered_bigrams(results, output_file, minimum_weight)

print(f"Success! Exported {saved_count} pairs to '{output_file}'.")