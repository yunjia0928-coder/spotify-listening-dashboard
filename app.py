import streamlit as st
import pandas as pd
import plotly.express as px

# Configure the app page
st.set_page_config(page_title = 'Your Spotify Highlight Dashboard', layout = 'wide')
# Create page title
st.title('Your Spotify Highlight Dashboard') 
# Create sidebar filters
st.sidebar.header('Filters')

audio_features = pd.read_json(
    'audio_features.json', 
    orient = 'index' # create dataframe with row by row lookup; outer JSON keys become DataFrame index
 ) 

# Part 1
# Load track dataset
spotify_tracks = pd.read_csv('spotify_tracks_data.csv')

# Drop near-duplicates that differ only in track_genre
compare_columns = [c for c in spotify_tracks.columns if c != 'track_genre']
spotify_tracks = spotify_tracks.drop_duplicates(
    subset = compare_columns
    ) # keep first (default) and compare all columns except 'track_genre'

# Load listening history and rename specific columns to match 'tracks' dataset
spotify_history = pd.read_csv('spotify_history.csv')
spotify_history = spotify_history.rename(columns={
   'spotify_track_uri': 'track_id',
   'artist_name': 'artists'
})

# Timestamp convert
spotify_history['ts'] = pd.to_datetime(
    spotify_history['ts'], errors = "coerce" # convert strings to pandas datetime; invalid values become NaT
    )
spotify_history = spotify_history.dropna(
    subset = ['ts']
)

# Create filters (boolean Series) for each applicable audio feature into dictionary
# Filter rows containing any out-of-range value of features
range_dict = audio_features['range'].dropna().to_dict()

# New series using the same label in spotify_tracks and initialize all values to "True"
final_filter = pd.Series(True, index = spotify_tracks.index) 

for feature in range_dict: # loop through 11 features
    lb = range_dict[feature][0]
    ub = range_dict[feature][1]
    valid_value = (spotify_tracks[feature] >= lb) & (spotify_tracks[feature] <= ub)
    final_filter = final_filter & valid_value # Compile valid results

# Drop any row that contains at least one audio feature value that is out-of-range
spotify_tracks = spotify_tracks[final_filter]

# Joining the datasets spotify_history and spotify_tracks 
history = set(spotify_history.columns)
track = set(spotify_tracks)
overlap = history & track
# Retain matching identifier 'track id'
overlap = overlap - {'track_id'}
# Drop duplicated column
spotify_tracks = spotify_tracks.drop(columns = overlap)
# Merge two dataframe
Final_playlist = spotify_history.merge(spotify_tracks, how = "left", on = 'track_id', indicator = True)
Final_playlist['matched'] = Final_playlist['_merge'] == 'both'
# Delete the original indicator after use
Final_playlist = Final_playlist.drop(columns = ['_merge'])
# check: print(Final_playlist['matched'].value_counts())
# check: print(Final_playlist)

# Part 2 Adding columns with derived values 
Final_playlist['date'] = Final_playlist['ts'].dt.date
Final_playlist['hour'] = Final_playlist['ts'].dt.hour
Final_playlist['min_played'] = Final_playlist['ms_played'] / 1000 / 60

def get_time_of_day(hour):
    if 5 <= hour < 12:
        return 'Morning'
    elif 12 <= hour < 18:
        return 'Afternoon'
    elif 18 <= hour < 21:
        return 'Evening'
    else:
        return 'Night'
Final_playlist['time_of_day'] = Final_playlist['hour'].apply(get_time_of_day)
#check: print(Final_playlist[['ts', 'date', 'hour', 'min_played', 'time_of_day']].head())

def get_mood(row):
    energy = row['energy']
    valence = row['valence']
    if pd.isna(valence) or pd.isna(energy):
        return 'Unknown'
    else:
        if valence >= 0.5:
            if energy >= 0.5:
                return 'Upbeat'
            else:
                return 'Calm'
        elif valence < 0.5:
            if energy >= 0.5:
                return 'Tense'
            else:
                return 'Mellow'
Final_playlist['mood'] = Final_playlist.apply(get_mood, axis = 1)

# Streamlit setup - START!
'''Hi! Here's your fav Spotify tracks✨'''
# Date range
min_date = Final_playlist['date'].min()
max_date = Final_playlist['date'].max()
# Date input as a range
selected_date = st.sidebar.date_input(
    'Date range', value = (min_date, max_date), 
    min_value = min_date, 
    max_value = max_date
    )

# Multiselect for “time_of_day” in "Final_playlist"
selected_time = st.sidebar.multiselect('Time of day',
sorted(Final_playlist['time_of_day'].unique()),
default=sorted(Final_playlist['time_of_day'].unique()),
)

# Checkbox of excluding “skipped” tracks
exclude_skipped = st.sidebar.checkbox('Do you want to exclude skipped tracks?', value = True)
# Checkbox of displaying only "matched" tracks
matched_only = st.sidebar.checkbox('Only display your matched tracks', value = True)

# Applying these filters to dataset
time_filter = Final_playlist['time_of_day'].isin(selected_time)
date_filter = (Final_playlist['date'] >= selected_date[0]) & (Final_playlist['date'] <= selected_date[1])
if exclude_skipped:
    skipped_filter = Final_playlist['skipped'] == False
else:
    skipped_filter = pd.Series(True, index = Final_playlist.index)  # Keep all rows in 'Final_playlist' when this filter is not applied
if matched_only:
    matched_filter = Final_playlist['matched'] == True
else:
    matched_filter = pd.Series(True, index = Final_playlist.index) 

overall_filters = (time_filter & date_filter & skipped_filter & matched_filter)
after_filtration = Final_playlist[overall_filters].copy()

# Create Streamlit headline metrics 
Tracks_played = len(after_filtration)
Hours_played = after_filtration['min_played'].sum() / 60
Unique_tracks = len(after_filtration['track_id'].unique())
Unique_artists = len(after_filtration['artists'].unique())

# Display these headline metrics on the dashbaord
# Create list of container objects, laid out side by side
c1, c2, c3, c4 = st.columns(4)

# Set up each col container to display a metric
c1.metric('Tracks played', f'{Tracks_played:,}')
c2.metric('Hours played', round(Hours_played, 1))
c3.metric('Unique track', f'{Unique_tracks:,}')
c4.metric('Unique artists', f'{Unique_artists:,}')


# Create data visualization 
#1 Average audio profile: radar chart 
# Finding feature names with type == 'float'
float_names = audio_features['type'] == 'float' # Boolean series
float_audio_features = audio_features[float_names] # Filtered dataframe containing rows named with 'float'
float_feature_names = float_audio_features.index
# Display the mean value of every audio feature, normalised to [0, 1]
# Extract all float audio feature columns in filtered Spotify data (after_filtration)
mean_float_feaures = after_filtration[float_feature_names].mean() # Series
# Radar normalization
norm_features = {}
for feature in float_feature_names:
    if feature in range_dict: # range of 'tempo' is NaN 
        LB = range_dict[feature][0]
        UB = range_dict[feature][1]
    else:
        LB = Final_playlist[feature].min() # implementation for 'tempo' range
        UB = Final_playlist[feature].max()
    norm_features[feature] = (mean_float_feaures[feature] - LB) / (UB - LB)

# Create 3 tabs for baseline and 2 for ecploratory
tab1, tab2, tab3, tab4, tab5 = st.tabs([ 'Average Audio Profile',
                                         'Mood',
                                         'Data',
                                         'Different Type of Me',
                                         'Similar Tracks Recommendation']
                                        )

# Establish radar figure for tab 1
with tab1:
    fig = px.line_polar(
        r = norm_features.values(),
        theta = norm_features.keys(),
        line_close = True
    )
    st.plotly_chart(fig, use_container_width=True)

# Establish mood chart excluding 'Unknown' for tab 2 (pie chart)
with tab2:
    mood_excluded_unknown = after_filtration['mood'] != 'Unknown'
    mood_display = after_filtration[mood_excluded_unknown]
    mood_counts = mood_display['mood'].value_counts() # Series
    mood_proportion = px.pie(names = mood_counts.index, values = mood_counts.values)
    st.plotly_chart(mood_proportion, use_container_width=True)

# Establish filtered data table and download button for tab 3
# All audio feature names add required columns
with tab3:
    filtered_table_col = (['track_name', 'artists', 'album_name', 'track_genre', 'mood']
                           + list(audio_features.index)  
                           + ['min_played', 'time_of_day', 'ts', 'skipped']
    )
    filtered_audio_table = after_filtration[filtered_table_col]
    st.dataframe(filtered_audio_table, use_container_width=True)
# Convert the filtered data to CSV and provide a download button
    csv_file = filtered_audio_table.to_csv(index = False)
    st.download_button(label = 'I want to download record!',
                       data = csv_file, 
                       file_name = 'My_Spotify_data.csv', 
                       mime = 'text/csv'
                       )

# Exploratory 1：Weekday vs Weekend Listening Analysis
# Check what day of the week is each record
day_of_week = after_filtration['ts'].dt.dayofweek # Series

def get_day_type(day):
    if day >= 5:
        return 'Weekend' 
    else:
        return 'Weekday' 
    
# Send each element into 'day'
after_filtration['day_type'] = day_of_week.apply(get_day_type)
# Count tracks played on each active listening day
daily_track = (after_filtration.groupby(['date', 'day_type']).size()) # Series
# Convert to DataFrame and name the count column
daily_track = daily_track.reset_index(name = 'track_played_counts')
# Calculate average: tracks of per active listening day by weekday and weekend
average_tracks_played = (daily_track.groupby('day_type'))['track_played_counts'].mean()
# weekday = 13.510442, weekend = 12.956897

# Different types of track of different day
day_type_audio_average = (after_filtration.groupby('day_type')[float_feature_names].mean())
# Normalization
norm_day_audio = day_type_audio_average.copy() # keep oringinal mean

for feature in float_feature_names:
    if feature in range_dict: # range of 'tempo' is NaN 
        LB = range_dict[feature][0]
        UB = range_dict[feature][1]
    else:
        LB = Final_playlist[feature].min() # implementation for 'tempo' range
        UB = Final_playlist[feature].max()
    norm_day_audio[feature] = (
        (day_type_audio_average[feature] - LB) / (UB - LB)
    )

# Compare Mood Preference
# Exclude Unknown mood from the current data with day_type
mood_day_display = after_filtration[
    after_filtration['mood'] != 'Unknown'
]
# Count types of mood of weekday and weekend
mood_day_counts = (mood_day_display.groupby(['day_type', 'mood']).size()) # Series

# Count total records with known mood for each day type
mood_day_total = (mood_day_display.groupby('day_type').size()) # Series

# Calculate proportion for different mood of different day types
# Convert to DataFrame and name the count column
mood_comparison = mood_day_counts.reset_index(name = 'mood_count') 
# Use day_type of each row in mood_comparison to search the value of data_type in mood_day_total
mood_comparison['total'] = mood_comparison['day_type'].map(mood_day_total)
mood_comparison['percentage'] = ((mood_comparison['mood_count']) / mood_comparison['total'] * 100)

with tab4:
    '''① Listening Activity'''
    day_of_week_fig = px.bar(x = average_tracks_played.index, 
                             y = average_tracks_played.values, 
                             labels = {'x': 'Day Type', 'y': 'Average Tracks / Active Day'},
                             title = 'Tracks I played on different type of day'
                             )
    st.plotly_chart(day_of_week_fig, use_container_width = True)

    '''② Audio Profile'''
    # Transpose for graph
    audio_comparison = norm_day_audio.T
    different_audio_fig = px.bar(
        audio_comparison, 
        barmode = 'group', 
        labels = {
            'index': 'Audio Feature', 
            'value': 'Normalized Mean', 
            'variable': 'Day Type'
        }, 
        title = 'Audio types I played of different day' 
    )
    st.plotly_chart(different_audio_fig, use_container_width=True)

    '''③ Mood Preference of Different Day'''
    mood_day_fig = px.bar(
        mood_comparison,
        x = 'percentage',
        y = 'day_type',
        color = 'mood',
        orientation = 'h',
        barmode = 'stack',
        labels = {
            'percentage': 'Percentage (%)',
            'day_type': 'Day Type',
            'mood': 'Mood'
        },
        title = 'My different mood: Weekday vs Weekend'
    )
    st.plotly_chart(mood_day_fig, use_container_width=True)


# Exploratory 2: Similar Track Finder — choose one track and find tracks with similar audio characteristics
with tab5:
    st.subheader('We know what you may like✨💖')

    # Keep one row for each candidate track
    track_candidates = after_filtration.drop_duplicates(subset=['track_id'])

    # Exclude tracks without complete audio features
    track_candidates = track_candidates.dropna(subset=float_feature_names)

    # Create a list of track names with available audio features
    track_options = track_candidates['track_name'].unique()

    # Let user select a track
    selected_track = st.selectbox(
        'Choose a track you want!',
        track_options
    )

    # Filter the selected track from candidate tracks
    selected_rows = track_candidates[
        track_candidates['track_name'] == selected_track
    ]

    # Extract the first row as a Series of audio features
    selected_audio = selected_rows[float_feature_names].iloc[0]

    # Create copies for normalization
    norm_candidates = track_candidates[float_feature_names].copy()
    norm_selected_audio = selected_audio.copy()

    # Normalize candidate tracks and selected track using the same ranges
    for feature in float_feature_names:
        if feature in range_dict:
            LB = range_dict[feature][0]
            UB = range_dict[feature][1]
        else:
            LB = Final_playlist[feature].min()
            UB = Final_playlist[feature].max()

        norm_candidates[feature] = (
            (track_candidates[feature] - LB) / (UB - LB)
        )

        norm_selected_audio[feature] = (
            (selected_audio[feature] - LB) / (UB - LB)
        )

    # Calculate the difference between each candidate and selected track
    difference = norm_candidates - norm_selected_audio

    # Square differences to prevent positive and negative values from cancelling out
    squared_difference = difference ** 2

    # Sum the squared differences across all 9 audio features for each track
    distance_sum = squared_difference.sum(axis=1)

    # Calculate Euclidean distance
    distance = distance_sum ** 0.5

    # Add similarity distance to candidate tracks
    track_candidates['distance'] = distance

    # Exclude the selected track itself
    recommendations = track_candidates[
        track_candidates['track_id'] != selected_rows['track_id'].iloc[0]
    ]

    # Rank tracks from most similar to least similar
    recommendations = recommendations.sort_values(by='distance')

    # Keep the top 5 most similar tracks
    recommendations = recommendations.head(5)

    # Select useful columns for display
    recommendation_display = recommendations[
        ['track_name', 'artists', 'track_genre', 'distance']
    ]

    # Display recommendations
    st.write('Top 5 tracks with similar audio characteristics:')
    st.dataframe(recommendation_display, use_container_width=True)
    st.caption('A smaller distance indicates a more similar audio profile.')








    







