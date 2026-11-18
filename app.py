import streamlit as st
import pandas as pd
import plotly.express as px

# Configure the app page
st.set_page_config(page_title = 'Your Spotify Highlight Dashboard', layout = 'wide')
# Create page title
st.title('Your Spotify Highlight Dashboard')
# Create sidebar filters
st.sidebar.header('Filters')

@st.cache_data
def load_and_process_data():
    audio_features = pd.read_json(
        'audio_features.json',
        orient = 'index'
    )

    # Part 1
    spotify_tracks = pd.read_csv('spotify_tracks_data.csv')

    compare_columns = [c for c in spotify_tracks.columns if c != 'track_genre']
    spotify_tracks = spotify_tracks.drop_duplicates(subset = compare_columns)

    spotify_history = pd.read_csv('spotify_history.csv')
    spotify_history = spotify_history.rename(columns={
        'spotify_track_uri': 'track_id',
        'artist_name': 'artists'
    })

    spotify_history['ts'] = pd.to_datetime(
        spotify_history['ts'], errors = 'coerce'
    )
    spotify_history = spotify_history.dropna(subset = ['ts'])

    range_dict = audio_features['range'].dropna().to_dict()
    final_filter = pd.Series(True, index = spotify_tracks.index)

    for feature in range_dict:
        lb = range_dict[feature][0]
        ub = range_dict[feature][1]
        valid_value = (
            (spotify_tracks[feature] >= lb)
            & (spotify_tracks[feature] <= ub)
        )
        final_filter = final_filter & valid_value

    spotify_tracks = spotify_tracks[final_filter]

    history = set(spotify_history.columns)
    track = set(spotify_tracks)
    overlap = (history & track) - {'track_id'}
    spotify_tracks = spotify_tracks.drop(columns = overlap)

    final_playlist = spotify_history.merge(
        spotify_tracks,
        how = 'left',
        on = 'track_id',
        indicator = True
    )
    final_playlist['matched'] = final_playlist['_merge'] == 'both'
    final_playlist = final_playlist.drop(columns = ['_merge'])

    # Part 2: derived columns
    final_playlist['date'] = final_playlist['ts'].dt.date
    final_playlist['hour'] = final_playlist['ts'].dt.hour
    final_playlist['min_played'] = final_playlist['ms_played'] / 1000 / 60

    def get_time_of_day(hour):
        if 5 <= hour < 12:
            return 'Morning'
        elif 12 <= hour < 18:
            return 'Afternoon'
        elif 18 <= hour < 21:
            return 'Evening'
        else:
            return 'Night'

    final_playlist['time_of_day'] = final_playlist['hour'].apply(get_time_of_day)

    def get_mood(row):
        energy = row['energy']
        valence = row['valence']
        if pd.isna(valence) or pd.isna(energy):
            return 'Unknown'
        if valence >= 0.5:
            if energy >= 0.5:
                return 'Upbeat'
            return 'Calm'
        if energy >= 0.5:
            return 'Tense'
        return 'Mellow'

    final_playlist['mood'] = final_playlist.apply(get_mood, axis = 1)

    return audio_features, final_playlist, range_dict


audio_features, final_playlist, range_dict = load_and_process_data()

# Streamlit setup
min_date = final_playlist['date'].min()
max_date = final_playlist['date'].max()

selected_date = st.sidebar.date_input(
    'Date range',
    value = (min_date, max_date),
    min_value = min_date,
    max_value = max_date
)

selected_time = st.sidebar.multiselect(
    'Time of day',
    sorted(final_playlist['time_of_day'].unique()),
    default = sorted(final_playlist['time_of_day'].unique())
)

exclude_skipped = st.sidebar.checkbox(
    'Do you want to exclude skipped tracks?',
    value = True
)
matched_only = st.sidebar.checkbox(
    'Only display your matched tracks',
    value = True
)

time_filter = final_playlist['time_of_day'].isin(selected_time)

if len(selected_date) == 2:
    start_date, end_date = selected_date
    date_filter = (
        (final_playlist['date'] >= start_date)
        & (final_playlist['date'] <= end_date)
    )
else:
    date_filter = pd.Series(True, index = final_playlist.index)

if exclude_skipped:
    skipped_filter = final_playlist['skipped'] == False
else:
    skipped_filter = pd.Series(True, index = final_playlist.index)

if matched_only:
    matched_filter = final_playlist['matched'] == True
else:
    matched_filter = pd.Series(True, index = final_playlist.index)

overall_filters = (
    time_filter & date_filter & skipped_filter & matched_filter
)
after_filtration = final_playlist[overall_filters].copy()

# Headline metrics
tracks_played = len(after_filtration)
hours_played = after_filtration['min_played'].sum() / 60
unique_tracks = len(after_filtration['track_id'].unique())
unique_artists = len(after_filtration['artists'].unique())

c1, c2, c3, c4 = st.columns(4)
c1.metric('Tracks played', f'{tracks_played:,}')
c2.metric('Hours played', round(hours_played, 1))
c3.metric('Unique track', f'{unique_tracks:,}')
c4.metric('Unique artists', f'{unique_artists:,}')

# Average audio profile
float_names = audio_features['type'] == 'float'
float_audio_features = audio_features[float_names]
float_feature_names = float_audio_features.index
mean_float_features = after_filtration[float_feature_names].mean()

norm_features = {}
for feature in float_feature_names:
    if feature in range_dict:
        lb = range_dict[feature][0]
        ub = range_dict[feature][1]
    else:
        lb = final_playlist[feature].min()
        ub = final_playlist[feature].max()
    norm_features[feature] = (
        (mean_float_features[feature] - lb) / (ub - lb)
    )

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    'Average Audio Profile',
    'Mood',
    'Data',
    'Different Type of Me',
    'Similar Tracks Recommendation'
])

with tab1:
    fig = px.line_polar(
        r = norm_features.values(),
        theta = norm_features.keys(),
        line_close = True
    )
    fig.update_layout(
        polar = dict(
            radialaxis = dict(range = [0, 1])
        )
    )
    st.plotly_chart(fig, use_container_width = True)

with tab2:
    mood_excluded_unknown = after_filtration['mood'] != 'Unknown'
    mood_display = after_filtration[mood_excluded_unknown]
    mood_counts = mood_display['mood'].value_counts()
    mood_proportion = px.pie(
        names = mood_counts.index,
        values = mood_counts.values
    )
    st.plotly_chart(mood_proportion, use_container_width = True)

with tab3:
    filtered_table_col = (
        ['track_name', 'artists', 'album_name', 'track_genre', 'mood']
        + list(audio_features.index)
        + ['min_played', 'time_of_day', 'ts', 'skipped']
    )
    filtered_audio_table = after_filtration[filtered_table_col]
    st.dataframe(filtered_audio_table, use_container_width = True)

    csv_file = filtered_audio_table.to_csv(index = False)
    st.download_button(
        label = 'I want to download record!',
        data = csv_file,
        file_name = 'My_Spotify_data.csv',
        mime = 'text/csv'
    )

# Exploratory 1: Weekday vs Weekend Listening Analysis
day_of_week = after_filtration['ts'].dt.dayofweek

def get_day_type(day):
    if day >= 5:
        return 'Weekend'
    return 'Weekday'

after_filtration['day_type'] = day_of_week.apply(get_day_type)

daily_track = after_filtration.groupby(['date', 'day_type']).size()
daily_track = daily_track.reset_index(name = 'track_played_counts')
average_tracks_played = (
    daily_track.groupby('day_type')['track_played_counts'].mean()
)

day_type_audio_average = (
    after_filtration.groupby('day_type')[float_feature_names].mean()
)
norm_day_audio = day_type_audio_average.copy()

for feature in float_feature_names:
    if feature in range_dict:
        lb = range_dict[feature][0]
        ub = range_dict[feature][1]
    else:
        lb = final_playlist[feature].min()
        ub = final_playlist[feature].max()
    norm_day_audio[feature] = (
        (day_type_audio_average[feature] - lb) / (ub - lb)
    )

mood_day_display = after_filtration[
    after_filtration['mood'] != 'Unknown'
]
mood_day_counts = (
    mood_day_display.groupby(['day_type', 'mood']).size()
)
mood_day_total = mood_day_display.groupby('day_type').size()

mood_comparison = mood_day_counts.reset_index(name = 'mood_count')
mood_comparison['total'] = (
    mood_comparison['day_type'].map(mood_day_total)
)
mood_comparison['percentage'] = (
    mood_comparison['mood_count']
    / mood_comparison['total']
    * 100
)

with tab4:
    st.write('① Listening Activity')
    day_of_week_fig = px.bar(
        x = average_tracks_played.index,
        y = average_tracks_played.values,
        labels = {
            'x': 'Day Type',
            'y': 'Average Tracks / Active Day'
        },
        title = 'Tracks I played on different type of day'
    )
    st.plotly_chart(day_of_week_fig, use_container_width = True)

    st.write('② Audio Profile')
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
    st.plotly_chart(different_audio_fig, use_container_width = True)

    st.write('③ Mood Preference of Different Day')
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
    st.plotly_chart(mood_day_fig, use_container_width = True)

# Exploratory 2: Similar Track Finder
with tab5:
    st.subheader('We know what you may like✨💖')

    track_candidates = after_filtration.drop_duplicates(
        subset = ['track_id']
    )
    track_candidates = track_candidates.dropna(
        subset = float_feature_names
    )
    track_options = track_candidates['track_name'].unique()

    selected_track = st.selectbox(
        'Choose a track you want!',
        track_options
    )

    selected_rows = track_candidates[
        track_candidates['track_name'] == selected_track
    ]
    selected_audio = selected_rows[float_feature_names].iloc[0]

    norm_candidates = track_candidates[float_feature_names].copy()
    norm_selected_audio = selected_audio.copy()

    for feature in float_feature_names:
        if feature in range_dict:
            lb = range_dict[feature][0]
            ub = range_dict[feature][1]
        else:
            lb = final_playlist[feature].min()
            ub = final_playlist[feature].max()

        norm_candidates[feature] = (
            (track_candidates[feature] - lb) / (ub - lb)
        )
        norm_selected_audio[feature] = (
            (selected_audio[feature] - lb) / (ub - lb)
        )

    difference = norm_candidates - norm_selected_audio
    squared_difference = difference ** 2
    distance_sum = squared_difference.sum(axis = 1)
    distance = distance_sum ** 0.5

    track_candidates['distance'] = distance

    recommendations = track_candidates[
        track_candidates['track_id']
        != selected_rows['track_id'].iloc[0]
    ]
    recommendations = recommendations.sort_values(by = 'distance')
    recommendations = recommendations.head(5)

    recommendation_display = recommendations[
        ['track_name', 'artists', 'track_genre', 'distance']
    ]

    st.write('Top 5 tracks with similar audio characteristics:')
    st.dataframe(
        recommendation_display,
        use_container_width = True
    )
    st.caption(
        'A smaller distance indicates a more similar audio profile.'
    )
