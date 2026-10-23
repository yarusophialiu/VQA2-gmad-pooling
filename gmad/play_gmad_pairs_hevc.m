function pairs = play_gmad_pairs_hevc(videoRoot, validateOnly, pairListFile)
% PLAY_GMAD_PAIRS_HEVC Inspect pilot pairs with Psychtoolbox (HEVC only).
%   play_gmad_pairs_hevc % latest 360p/480p pilot: 14 pairs / 22 videos
%   play_gmad_pairs_hevc('C:\path\to\pilot_videos_360p480p_120fps')
%   pairs = play_gmad_pairs_hevc([], true); % Validate files without a window.
%   play_gmad_pairs_hevc(videoRoot, false, 'C:\path\to\pilot_pairs.csv')
%
% Left: restart A. Right: restart B. Enter: next pair, with a 0.5 s black
% screen. Escape: quit. Finished videos hold their final frame until a key.
% Labels show the SOURCE chunk settings; assembled files are 1080p/120 fps.
% Requires Psychtoolbox and GStreamer with a working HEVC decoder:
% https://psychtoolbox.org/docs/Screen-OpenMovie
% Movie timestamps: https://psychtoolbox.org/docs/Screen-GetMovieImage

%% User settings
FULL_SCREEN = false; % false; true             % true: fullscreen; false: windowed
SCREEN_NUMBER = [];               % []: highest screen number, or set 0/1/...
WINDOW_RECT = [100 100 1380 820];   % Windowed position/size (1280 x 720)
BLANK_SECONDS = 0.5;
START_PAIR = 1;
TEXT_SIZE = 22;
SKIP_SYNC_TESTS = ~FULL_SCREEN;    % Windowed preview; fullscreen checks sync
GSTREAMER_BIN = 'C:\gstreamer\1.0\msvc_x86_64\bin'; % '' uses the existing PATH

workspace = fileparts(fileparts(fileparts(mfilename('fullpath'))));
usingDefaultVideos = nargin < 1 || isempty(videoRoot);
if usingDefaultVideos
    videoRoot = fullfile(workspace, 'VQA2-dataset', 'pilot_videos_360p480p_120fps');
end
if nargin < 2
    validateOnly = false;
end
videoRoot = char(videoRoot);
% Accept either the parent directory or its bistro subdirectory. Resolve
% filenames relative to their CURRENT location, never the old manifest paths.
if isfile(fullfile(videoRoot, 'pilot_pairs_bistro.csv'))
    videoDir = videoRoot;
else
    videoDir = fullfile(videoRoot, 'bistro');
end
if nargin < 3 || isempty(pairListFile)
    if usingDefaultVideos
        % Read the latest result CSV directly, including subsequent edits.
        pairListFile = fullfile(workspace, 'VQA2-gmad-pooling', 'results', ...
            'gmad_bistro_360p480p_skip_negative_no_offset_time_converted', 'pilot_pairs.csv');
    else
        pairListFile = fullfile(videoDir, 'pilot_pairs_bistro.csv');
    end
end
csvFile = char(pairListFile);
assert(isfile(csvFile), 'gmad:MissingPairs', 'Cannot find pair list: %s', csvFile);
pairs = readtable(csvFile, 'TextType', 'string', 'VariableNamingRule', 'preserve');
required = {'pair_id', 'scene', 'video_a', 'video_b', 'settings_a', ...
    'settings_b', 'gmad_task_count'};
assert(all(ismember(required, pairs.Properties.VariableNames)), ...
    'gmad:InvalidPairs', 'Pair list is missing required columns.');
assert(height(pairs) > 0 && all(pairs.scene == "bistro"), ...
    'gmad:InvalidPairs', 'Expected a nonempty bistro pilot list.');
assert(numel(unique(pairs.pair_id)) == height(pairs), ...
    'gmad:DuplicatePair', 'Pair IDs must be unique.');
assert(isnumeric(pairs.gmad_task_count) && all(isfinite(pairs.gmad_task_count)) ...
    && all(pairs.gmad_task_count >= 0), 'gmad:InvalidTasks', 'Invalid linked-task counts.');
assert(START_PAIR >= 1 && START_PAIR <= height(pairs), 'gmad:StartPair', 'Invalid START_PAIR.');

paths = strings(height(pairs), 2);
sourceSettings = cell(height(pairs), 2);
for pairIndex = 1:height(pairs)
    for side = 1:2
        sideName = char('a' + side - 1);
        candidate = pairs.(['video_' sideName])(pairIndex);
        assert(~contains(candidate, ["/", "\", ".."]) && startsWith(candidate, "bistro__"), ...
            'gmad:InvalidCandidate', 'Unexpected video identifier: %s', candidate);
        paths(pairIndex, side) = fullfile(videoDir, candidate + ".mp4");
        assert(isfile(paths(pairIndex, side)), 'gmad:MissingVideo', ...
            'Missing HEVC video: %s', paths(pairIndex, side));
        labels = strtrim(split(pairs.(['settings_' sideName])(pairIndex), '/'));
        assert(numel(labels) == 3, 'gmad:InvalidSettings', 'Expected three chunk settings.');
        settings = zeros(3, 3);
        for sourceChunk = 1:3
            token = regexp(char(labels(sourceChunk)), '^(360|480|720|1080)p(30|60|120)$', 'tokens', 'once');
            assert(~isempty(token), 'gmad:InvalidSettings', 'Invalid chunk setting: %s', labels(sourceChunk));
            h = str2double(token{1});
            heights = [360 480 720 1080];
            widths = [640 854 1280 1920];
            settings(sourceChunk, :) = [widths(heights == h), h, str2double(token{2})];
        end
        assert(candidate == "bistro__" + strjoin(labels, '-'), ...
            'gmad:SettingsMismatch', 'Candidate identifier and settings disagree: %s', candidate);
        sourceSettings{pairIndex, side} = settings;
    end
end
% Confirm these are the HEVC originals, not H.264 copies. This uses metadata
% beside each rendered MP4 and does not require ffprobe or a video decoder.
uniquePaths = unique(paths(:), 'stable');
for i = 1:numel(uniquePaths)
    [folder, name] = fileparts(uniquePaths(i));
    metadataFile = fullfile(folder, name + ".render.json");
    assert(isfile(metadataFile), 'gmad:MissingMetadata', 'Missing render metadata: %s', metadataFile);
    metadata = jsondecode(fileread(metadataFile));
    info = metadata.probe;
    assert(strcmp(info.codec_name, 'hevc') && info.width == 1920 && info.height == 1080 ...
        && strcmp(info.avg_frame_rate, '120/1') && str2double(string(info.nb_frames)) == 540 ...
        && abs(str2double(string(info.duration)) - 4.5) < 1e-5, ...
        'gmad:UnexpectedVideo', 'Expected 1080p/120 fps/4.5 s HEVC: %s', uniquePaths(i));
end
fprintf('Validated %d pairs / %d HEVC videos in %s\n', height(pairs), numel(uniquePaths), videoDir);
fprintf('Pair list: %s\n', csvFile);
if validateOnly
    return;
end
assert(exist('Screen', 'file') ~= 0 && exist('KbQueueCreate', 'file') ~= 0, ...
    'gmad:MissingPsychtoolbox', 'Psychtoolbox is not on the MATLAB path. Run your PTB setup first.');

% Resource cleanup runs on Escape, normal completion, errors, and Ctrl+C.
window = [];
movies = nan(numel(uniquePaths), 1);
movieSizes = zeros(numel(uniquePaths), 2);
texture = [];
oldPath = getenv('PATH');
% A handle map survives function unwinding; an external cleanup function can
% safely access it even on Ctrl+C (unlike an onCleanup nested-function closure).
resources = containers.Map('KeyType', 'char', 'ValueType', 'any');
resources('window') = [];
resources('movies') = movies;
resources('texture') = [];
resources('queueCreated') = false;
resources('oldSkipSync') = [];
resources('oldPath') = oldPath;
cleanupGuard = onCleanup(@() cleanupResources(resources));
if ~isempty(GSTREAMER_BIN)
    assert(isfolder(GSTREAMER_BIN), 'gmad:MissingGStreamer', 'Missing GSTREAMER_BIN directory.');
    setenv('PATH', [GSTREAMER_BIN pathsep oldPath]);
end
KbName('UnifyKeyNames');
keys.left = KbName('LeftArrow');
keys.right = KbName('RightArrow');
keys.enter = KbName('Return');
keys.escape = KbName('ESCAPE');
keyList = zeros(1, 256);
keyList([keys.left keys.right keys.enter keys.escape]) = 1;
resources('oldSkipSync') = Screen('Preference', 'SkipSyncTests', double(SKIP_SYNC_TESTS));
screens = Screen('Screens');
if isempty(SCREEN_NUMBER)
    SCREEN_NUMBER = max(screens);
end
assert(ismember(SCREEN_NUMBER, screens), 'gmad:ScreenNumber', 'Requested screen is unavailable.');
if FULL_SCREEN
    [window, windowRect] = Screen('OpenWindow', SCREEN_NUMBER, 0);
else
    [window, windowRect] = Screen('OpenWindow', SCREEN_NUMBER, 0, WINDOW_RECT);
end
resources('window') = window;
HideCursor;
Screen('TextFont', window, 'Arial');
Screen('TextSize', window, TEXT_SIZE);
refreshRate = 1 / Screen('GetFlipInterval', window);
fprintf('Display refresh: %.2f Hz. Movie files: 120 fps.\n', refreshRate);

% Open all selected files at startup, without preloading whole movies. This avoids
% reopening files during the timed black screen or A/B switches.
for i = 1:numel(uniquePaths)
    Screen('FillRect', window, 0);
    Screen('DrawText', window, sprintf('Opening HEVC videos: %d / %d', i, numel(uniquePaths)), ...
        30, 30, [255 255 255]);
    Screen('Flip', window);
    try
        [movies(i), duration, fps, w, h] = Screen('OpenMovie', window, char(uniquePaths(i)), 0, 0);
        resources('movies') = movies;
    catch cause
        failure = MException('gmad:HEVCDecoder', ...
            'Psychtoolbox could not decode HEVC. Check GStreamer HEVC support. File: %s', uniquePaths(i));
        throw(addCause(failure, cause));
    end
    assert(abs(duration - 4.5) < 0.05 && abs(fps - 120) < 0.1 && w == 1920 && h == 1080, ...
        'gmad:MovieFormat', 'Unexpected decoded movie properties: %s', uniquePaths(i));
    movieSizes(i, :) = [w h];
end
[~, movieLookup] = ismember(paths, uniquePaths);
KbReleaseWait;
KbQueueCreate([], keyList);
resources('queueCreated') = true;
KbQueueStart;
KbQueueFlush;
pairIndex = START_PAIR;
side = 1;
quit = false;
fprintf('Left=A; Right=B; Enter=next pair (0.5 s black); Escape=quit.\n');

while ~quit
    movieIndex = movieLookup(pairIndex, side);
    movie = movies(movieIndex);
    destination = fitMovieRect(movieSizes(movieIndex, :), windowRect);
    Screen('SetMovieTimeIndex', movie, 0);
    Screen('PlayMovie', movie, 1, 0, 0);
    ended = false;
    lastPTS = 0;
    action = '';
    while isempty(action)
        % Nonblocking fetch keeps keyboard input responsive during decoding.
        if ~ended
            [newTexture, pts] = Screen('GetMovieImage', window, movie, 0);
            if newTexture > 0
                if ~isempty(texture)
                    Screen('Close', texture);
                end
                texture = newTexture;
                resources('texture') = texture;
                lastPTS = pts;
                drawFrame(destination, lastPTS, false);
                Screen('Flip', window);
            elseif newTexture < 0
                ended = true;
                dropped = Screen('PlayMovie', movie, 0);
                fprintf('%s / %c: finished, decoder dropped frames = %d\n', ...
                    pairs.pair_id(pairIndex), char('A' + side - 1), dropped);
                drawFrame(destination, lastPTS, true);
                Screen('Flip', window);
            else
                WaitSecs('YieldSecs', 0.001);
            end
        else
            WaitSecs('YieldSecs', 0.002);
        end
        action = readAction();
    end
    if ~ended
        dropped = Screen('PlayMovie', movie, 0);
        fprintf('%s / %c: stopped at %.3f s, decoder dropped frames = %d\n', ...
            pairs.pair_id(pairIndex), char('A' + side - 1), lastPTS, dropped);
    end
    if ~isempty(texture)
        Screen('Close', texture);
        texture = [];
        resources('texture') = [];
    end
    if strcmp(action, 'quit')
        quit = true;
        continue;
    end

    % Pure black: no text, labels, or old video frame. Holding it until the
    % next flip preserves at least BLANK_SECONDS on the physical display.
    Screen('FillRect', window, 0);
    blankOnset = Screen('Flip', window);
    if strcmp(action, 'next')
        deadline = blankOnset + BLANK_SECONDS;
        while GetSecs < deadline
            if strcmp(readAction(), 'quit')
                quit = true;
                break;
            end
            WaitSecs('YieldSecs', 0.001);
        end
        if quit
            continue;
        end
        pairIndex = pairIndex + 1;
        if pairIndex > height(pairs)
            fprintf('All %d pairs completed.\n', height(pairs));
            break;
        end
        side = 1; % Every new pair starts at A.
    elseif strcmp(action, 'a')
        side = 1;
    elseif strcmp(action, 'b')
        side = 2;
    end
    KbQueueFlush;
end

    function action = readAction()
        action = '';
        [pressed, ~, ~, lastPress] = KbQueueCheck;
        if ~pressed
            return;
        end
        if lastPress(keys.escape) > 0
            action = 'quit';
            return;
        end
        codes = [keys.left keys.right keys.enter];
        [time, selected] = max(lastPress(codes));
        if time > 0
            actions = {'a', 'b', 'next'};
            action = actions{selected};
        end
    end

    function drawFrame(destination, pts, ended)
        Screen('FillRect', window, 0);
        if ~isempty(texture)
            Screen('DrawTexture', window, texture, [], destination);
        end
        % Use decoded presentation timestamp, not wall-clock elapsed time.
        activeChunk = min(3, max(1, floor((pts + 1e-6) / 1.5) + 1));
        setting = sourceSettings{pairIndex, side}(activeChunk, :);
        text = sprintf(['Pair %d/%d  %s   Video %c\n' ...
            'Chunk %d/3 source: %d x %d | %d fps\n' ...
            'Linked gMAD tasks: %d\n' ...
            'Left: A   Right: B   Enter: next   Esc: quit'], ...
            pairIndex, height(pairs), pairs.pair_id(pairIndex), char('A' + side - 1), ...
            activeChunk, setting(1), setting(2), setting(3), pairs.gmad_task_count(pairIndex));
        if ended
            text = [text sprintf('\nFinished - choose A/B to replay or Enter to continue.')];
        end
        x = destination(1) + 12;
        y = destination(2) + 12;
        lines = strsplit(text, newline);
        widths = zeros(1, numel(lines));
        for line = 1:numel(lines)
            bounds = Screen('TextBounds', window, lines{line});
            widths(line) = bounds(3) - bounds(1);
        end
        labelWidth = min(destination(3) - x, max(widths) + 16);
        labelHeight = numel(lines) * (TEXT_SIZE + 7) + 12;
        Screen('FillRect', window, [0 0 0], [x-6 y-6 x+labelWidth y+labelHeight]);
        for line = 1:numel(lines)
            Screen('DrawText', window, lines{line}, x, y + (line-1)*(TEXT_SIZE+7), [255 255 255]);
        end
    end

end

function destination = fitMovieRect(movieSize, windowRect)
% Preserve aspect ratio; show at 1080p size (1920x1080 box) centred on black.
% Never enlarged past 1080p, only shrunk to fit a smaller window.
windowSize = windowRect(3:4) - windowRect(1:2);
drawSize = movieSize * min([1920 1080] ./ movieSize);
drawSize = drawSize * min([1, windowSize ./ drawSize]);
origin = (windowSize - drawSize) / 2;
destination = [origin origin + drawSize];
end

function cleanupResources(resources)
if resources('queueCreated')
    try KbQueueRelease; catch, end
end
texture = resources('texture');
if ~isempty(texture)
    try Screen('Close', texture); catch, end
end
movies = resources('movies');
for handle = movies(isfinite(movies))'
    try Screen('PlayMovie', handle, 0); catch, end
    try Screen('CloseMovie', handle); catch, end
end
window = resources('window');
if ~isempty(window)
    try Screen('Close', window); catch, end
    try ShowCursor; catch, end
end
oldSkipSync = resources('oldSkipSync');
if ~isempty(oldSkipSync)
    try Screen('Preference', 'SkipSyncTests', oldSkipSync); catch, end
end
setenv('PATH', resources('oldPath'));
end
