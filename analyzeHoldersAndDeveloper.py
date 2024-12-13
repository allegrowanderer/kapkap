import pandas as pd
import os
from datetime import datetime

def get_wallet_category(row):
    """Determine wallet category based on various criteria"""
    # Check Contract first
    if row['Address Type'] == 'Contract':
        return 'Contract'
    
    # Check for fresh wallets (less than 7 days old) for all non-contract addresses
    if row['Wallet Age (days)'] < 7:
        return 'Fresh Wallet'
    
    # For regular users
    if pd.isna(row['Base TX (30d)']):
        return ''
        
    tx_count = int(str(row['Base TX (30d)']).replace('+', ''))
    
    # Check other criteria
    if tx_count > 9999:
        return 'Bot'
    elif tx_count > 1000:
        return 'Likely Bot'
    elif row['Wallet Age (days)'] == 0:
        return 'Sniper'
    elif (row['Has ETH NFTs'] == True and 
          row['Wallet Age (days)'] > 360 and 
          tx_count < 1000):
        return 'OG'
    
    return ''

def analyze_csvs():
    """Analyze holders and developer CSVs and create a combined report"""
    # Get list of CSV files in current directory
    csv_files = [f for f in os.listdir() if f.endswith('.csv')]
    
    # Separate holder and developer files
    holder_files = [f for f in csv_files if 'holders' in f]
    developer_files = [f for f in csv_files if 'deployer' in f]
    
    if not holder_files or not developer_files:
        print("Could not find required CSV files.")
        return
    
    # Get most recent files
    latest_holder_file = max(holder_files, key=os.path.getctime)
    latest_developer_file = max(developer_files, key=os.path.getctime)
    
    # Extract token name from filename
    token_name = latest_holder_file.split('_holders_')[0]
    
    # Clean up old summary files for this token
    cleanup_old_files(token_name)
    
    print(f"Processing files:\n{latest_holder_file}\n{latest_developer_file}")
    
    # Read CSVs
    holders_df = pd.read_csv(latest_holder_file)
    developer_df = pd.read_csv(latest_developer_file)
    
    # Change developer's Address Type to 'Developer'
    developer_df['Address Type'] = 'Developer'
    
    # Combine dataframes and remove duplicates based on Address
    combined_df = pd.concat([holders_df, developer_df], ignore_index=True)
    combined_df = combined_df.drop_duplicates(subset=['Address'], keep='last')
    
    # Fill missing boolean columns with False
    bool_columns = ['Older than 30d', 'Older than 90d', 'Older than 180d', 
                   'Older than 360d', 'Has Base NFTs', 'Has ETH NFTs']
    for col in bool_columns:
        combined_df[col] = combined_df[col].fillna(False)
    
    # Update age-related columns based on Wallet Age (days)
    combined_df['Older than 30d'] = combined_df['Wallet Age (days)'] > 30
    combined_df['Older than 90d'] = combined_df['Wallet Age (days)'] > 90
    combined_df['Older than 180d'] = combined_df['Wallet Age (days)'] > 180
    combined_df['Older than 360d'] = combined_df['Wallet Age (days)'] > 360
    
    # Add new analysis columns
    combined_df['Wallet Category'] = combined_df.apply(get_wallet_category, axis=1)
    
    # Calculate Token Balance Normalized
    max_balance = combined_df['Token Balance'].max()
    combined_df['Token Balance (Normalized)'] = combined_df['Token Balance'] / max_balance if max_balance > 0 else 0
    
    # Clean and calculate Activity Score
    def clean_tx_count(x):
        if pd.isna(x):
            return 0
        return int(str(x).replace('+', ''))

    base_tx = combined_df['Base TX (30d)'].apply(clean_tx_count)
    eth_tx = combined_df['ETH TX (30d)'].apply(clean_tx_count)
    max_tx = max(base_tx.max(), eth_tx.max())
    
    combined_df['Activity Score'] = (base_tx * 0.6 + eth_tx * 0.4) / max_tx if max_tx > 0 else 0
    
    # Generate summary statistics
    summary_stats = {
        'Total Wallets Analyzed': len(combined_df),
        'Total Supply Coverage': f"{combined_df['% of Total Supply'].str.rstrip('%').astype(float).sum():.2f}%",
        'Category Distribution': combined_df['Wallet Category'].value_counts().to_dict(),
        'Average Wallet Age': combined_df[combined_df['Address Type'] != 'Contract']['Wallet Age (days)'].mean(),
        'NFT Holders': {
            'Base': combined_df['Has Base NFTs'].sum(),
            'ETH': combined_df['Has ETH NFTs'].sum()
        }
    }
    
    # Save enhanced analysis
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    token_name = latest_holder_file.split('_holders_')[0]
    output_file = f"{token_name}_analysis_{timestamp}.csv"
    summary_file = f"{token_name}_summary_{timestamp}.txt"
    
    # Sort the dataframe by Token Balance in descending order
    combined_df = combined_df.sort_values('Token Balance', ascending=False)
    
    # Save detailed analysis CSV
    combined_df.to_csv(output_file, index=False)
    
    # Save summary report
    with open(summary_file, 'w') as f:
        f.write(f"Analysis Summary for {token_name}\n")
        f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        f.write("Overall Statistics:\n")
        f.write(f"Total Wallets Analyzed: {summary_stats['Total Wallets Analyzed']}\n")
        f.write(f"Total Supply Coverage: {summary_stats['Total Supply Coverage']}\n")
        f.write(f"Average Wallet Age: {summary_stats['Average Wallet Age']:.2f} days\n\n")
        
        f.write("Wallet Categories:\n")
        for category, count in summary_stats['Category Distribution'].items():
            if category:  # Only show non-empty categories
                percentage = (count / summary_stats['Total Wallets Analyzed']) * 100
                f.write(f"{category}: {count} ({percentage:.2f}%)\n")
        
        f.write("\nNFT Holdings:\n")
        f.write(f"Base NFT Holders: {summary_stats['NFT Holders']['Base']}\n")
        f.write(f"ETH NFT Holders: {summary_stats['NFT Holders']['ETH']}\n")
    
    print(f"\nAnalysis complete!")
    print(f"Detailed report saved as: {output_file}")
    print(f"Summary report saved as: {summary_file}")
    
    return combined_df, summary_stats

def cleanup_old_files(token_name):
    """Clean up old analysis and summary files for a given token"""
    try:
        # Get list of all files
        all_files = os.listdir()
        
        # Find files related to this token
        token_files = [f for f in all_files if f.startswith(token_name) and 
                      ('_summary_' in f or '_analysis_' in f or '_connections_' in f)]
        
        # Group files by type
        file_groups = {
            'summary': [f for f in token_files if '_summary_' in f],
            'analysis': [f for f in token_files if '_analysis_' in f],
            'connections': [f for f in token_files if '_connections_' in f]
        }
        
        # Keep only the most recent file of each type
        for file_type, files in file_groups.items():
            if len(files) > 1:
                # Sort by creation time, newest first
                files.sort(key=lambda x: os.path.getctime(x), reverse=True)
                # Remove all but the newest file
                for old_file in files[1:]:
                    try:
                        os.remove(old_file)
                        print(f"Removed old {file_type} file: {old_file}")
                    except Exception as e:
                        print(f"Error removing {old_file}: {str(e)}")
                
    except Exception as e:
        print(f"Error during cleanup: {str(e)}")

if __name__ == "__main__":
    analyze_csvs()  