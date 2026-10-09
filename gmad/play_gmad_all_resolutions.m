function pairs = play_gmad_all_resolutions(validateOnly, pairListFile, chunkRoot, previewOnly)
% PLAY_GMAD_ALL_RESOLUTIONS Play the latest bistro pilot directly from HEVC.
%   play_gmad_all_resolutions
%   pairs = play_gmad_all_resolutions(true); % Check list and source paths only.
%   play_gmad_all_resolutions(false, 'C:\path\to\pilot_pairs.csv');
%   play_gmad_all_resolutions(false, [], [], true); % Windowed preview override
% No concatenated MP4s are needed. Stream native-resolution HEVC frames and
% display three consecutive 1.5 s chunks, keeping at most seven textures.
% Left = restart A; Right = restart B; Enter = next pair; Escape = quit.
% Stopped-movie GetMovieImage calls decode sequentially on demand. Holding
% native frames preserves 30/60/120 fps sampling without caching full clips.

%% User settings
FULL_SCREEN = true; % fa
%
%
% lse;              % true: fullscreen; false: windowed preview
SCREEN_NUMBER = [];               % []: highest screen number
WINDOW_RECT = [100 100 1380 820];   % 1280 x 720 window
BLANK_SECONDS = 0.5;
START_PAIR = 1;
TEXT_SIZE = 22;
SKIP_SYNC_TESTS = ~FULL_SCREEN;
GSTREAMER_BIN = 'C:\gstreamer\1.0\msvc_x86_64\bin';

% Explicit preview override leaves the user's fullscreen configuration intact.
if nargin >= 4 && previewOnly
    FULL_SCREEN = false;
    SKIP_SYNC_TESTS = true;
end

workspace = fileparts(fileparts(fileparts(mfilename('fullpath'))));
if nargin < 1, validateOnly = false; end
if nargin < 2 || isempty(pairListFile)
    pairListFile = fullfile(workspace, 'VQA2-gmad-pooling', 'results', ...
        'gmad_bistro_all_resolutions_skip_negative_no_offset_time_converted', 'pilot_pairs.csv');
end
defaultRoot = nargin < 3 || isempty(chunkRoot);
if defaultRoot
    chunkRoot = fullfile(workspace, 'VQA2-dataset', 'gmad_frame_scores', ...
        'lossless_spatiotemporal_chunks', 'bistro', 'bistro_path2_seg3_1', 'videos');
end
assert(isfile(pairListFile), 'gmad:MissingPairs', 'Missing pair list: %s', pairListFile);
pairs = readtable(pairListFile, 'TextType', 'string', 'VariableNamingRule', 'preserve');
required = {'pair_id','scene','video_a','video_b','settings_a','settings_b','gmad_task_count'};
assert(all(ismember(required, pairs.Properties.VariableNames)) && height(pairs) > 0, ...
    'gmad:InvalidPairs', 'Expected a nonempty pilot list with the required columns.');
assert(all(pairs.scene == "bistro") && numel(unique(pairs.pair_id)) == height(pairs), ...
    'gmad:InvalidPairs', 'Expected bistro pairs with unique IDs.');
assert(isnumeric(pairs.gmad_task_count) && all(isfinite(pairs.gmad_task_count)) ...
    && all(pairs.gmad_task_count >= 0), 'gmad:InvalidTasks', 'Invalid linked-task counts.');
assert(START_PAIR >= 1 && START_PAIR <= height(pairs), 'gmad:StartPair', 'Invalid START_PAIR.');
paths = strings(height(pairs), 2, 3);
settings = cell(height(pairs), 2);
for p = 1:height(pairs)
    for s = 1:2
        suffix = char('a' + s - 1);
        labels = strtrim(split(pairs.(['settings_' suffix])(p), '/'));
        assert(numel(labels) == 3, 'gmad:InvalidSettings', 'Expected three chunks.');
        assert(pairs.(['video_' suffix])(p) == "bistro__" + strjoin(labels, '-'), ...
            'gmad:SettingsMismatch', 'Candidate identifier and settings disagree.');
        specification = zeros(3, 3);
        for c = 1:3
            token = regexp(char(labels(c)), '^(360|480|720|1080)p(30|60|120)$', 'tokens', 'once');
            assert(~isempty(token), 'gmad:InvalidSettings', 'Invalid setting: %s', labels(c));
            h = str2double(token{1});
            heights = [360 480 720 1080]; widths = [640 854 1280 1920];
            specification(c,:) = [widths(heights == h), h, str2double(token{2})];
            paths(p,s,c) = fullfile(chunkRoot, sprintf('chunk%d_%s_lossless_hevc.mp4', c, labels(c)));
            % Same pixels as the original, with the last packet duration
            % corrected. This is also the reference used by this CVVDP run.
            if defaultRoot && c == 1 && labels(c) == "1080p120"
                paths(p,s,c) = fullfile(workspace, 'VQA2-dataset', 'gmad_frame_scores', ...
                    'bistro_360p480p', 'bistro', 'bistro_path2_seg3_1', ...
                    'references', 'ref_chunk1_lossless_hevc.mp4');
            end
            assert(isfile(paths(p,s,c)), 'gmad:MissingChunk', 'Missing HEVC chunk: %s', paths(p,s,c));
        end
        settings{p,s} = specification;
    end
end
fprintf('Validated %d pairs / %d candidates / %d HEVC source chunks.\n', ...
    height(pairs), numel(unique([pairs.video_a; pairs.video_b])), numel(unique(paths(:))));
fprintf('Pair list: %s\n', pairListFile);
if validateOnly, return; end
assert(exist('Screen', 'file') ~= 0, 'gmad:MissingPsychtoolbox', 'Psychtoolbox is not on the MATLAB path.');

% A handle map makes resource cleanup safe during errors and Ctrl+C.
resources = containers.Map('KeyType', 'char', 'ValueType', 'any');
resources('window') = []; resources('movies') = [];
resources('textures') = []; resources('queueCreated') = false;
resources('oldSkipSync') = []; resources('oldPath') = getenv('PATH');
cleanupGuard = onCleanup(@() cleanupResources(resources));
if ~isempty(GSTREAMER_BIN)
    assert(isfolder(GSTREAMER_BIN), 'gmad:MissingGStreamer', 'Missing GSTREAMER_BIN.');
    setenv('PATH', [GSTREAMER_BIN pathsep resources('oldPath')]);
end
KbName('UnifyKeyNames');
keys = [KbName('LeftArrow'), KbName('RightArrow'), KbName('Return'), KbName('ESCAPE')];
keyList = zeros(1,256); keyList(keys) = 1;
resources('oldSkipSync') = Screen('Preference', 'SkipSyncTests', double(SKIP_SYNC_TESTS));
screens = Screen('Screens');
if isempty(SCREEN_NUMBER), SCREEN_NUMBER = max(screens); end
assert(ismember(SCREEN_NUMBER, screens), 'gmad:ScreenNumber', 'Requested screen unavailable.');
if FULL_SCREEN
    [window, rect] = Screen('OpenWindow', SCREEN_NUMBER, 0);
else
    [window, rect] = Screen('OpenWindow', SCREEN_NUMBER, 0, WINDOW_RECT);
end
resources('window') = window;
HideCursor;
Screen('TextFont', window, 'Arial'); Screen('TextSize', window, TEXT_SIZE);
ifi = Screen('GetFlipInterval', window);
fprintf('Display refresh: %.2f Hz. Native frames held at 30 / 60 / 120 fps.\n', 1/ifi);
fprintf('Left=A; Right=B; Enter=next; Escape=quit.\n');
KbQueueCreate([], keyList); resources('queueCreated') = true; KbQueueStart;
windowSize = rect(3:4) - rect(1:2);
drawSize = [1920 1080] * min(windowSize ./ [1920 1080]);
origin = (windowSize - drawSize) / 2;
destination = [origin origin + drawSize];

for p = START_PAIR:height(pairs)
    % Keep only one current texture per source (at most six), rather than
    % hundreds of textures holding decoder buffers and exhausting memory.
    releasePair(resources);
    [sources, ~, lookup] = unique(reshape(paths(p,:,:), 2, 3), 'stable');
    lookup = reshape(lookup, 2, 3);
    movies = nan(1, numel(sources));
    textures = zeros(1, numel(sources));
    frameIndex = zeros(1, numel(sources));
    lastPTS = -inf(1, numel(sources));
    resources('textures') = textures;
    for i = 1:numel(sources)
        [s,c] = find(lookup == i, 1);
        spec = settings{p,s}(c,:);
        Screen('FillRect', window, 0);
        Screen('DrawText', window, sprintf('Loading pair %d/%d: HEVC chunk %d/%d (Esc: quit)', ...
            p, height(pairs), i, numel(sources)), 30, 30, [255 255 255]);
        Screen('Flip', window);
        [movie, duration, fps, w, h] = Screen('OpenMovie', window, char(sources(i)), 0, 1);
        movies(i) = movie;
        resources('movies') = movies;
        assert(w == spec(1) && h == spec(2) && abs(fps-spec(3)) < 1 ...
            && abs(duration-1.5) < 0.02, 'gmad:MovieFormat', 'Unexpected movie properties: %s', sources(i));
        Screen('SetMovieTimeIndex', movie, 0);
        [pressed, ~, codes] = KbCheck;
        if pressed && codes(keys(4)), return; end
        [textures(i), lastPTS(i)] = fetchFrame(window, movie, sources(i), 1, resources, i);
        frameIndex(i) = 1;
        fprintf('Opened pair %d, %s (%dx%d, %d fps); caching one frame.\n', ...
            p, sources(i), w, h, spec(3));
    end
    KbQueueFlush;
    fprintf('READY pair %d/%d: %s\n', p, height(pairs), pairs.pair_id(p));
    side = 1;
    while true
        % Rewind only this side's decoders for A/B replay. No full-video load.
        for c = 1:3
            i = lookup(side,c);
            if frameIndex(i) ~= 1
                Screen('SetMovieTimeIndex', movies(i), 0);
                [textures(i), lastPTS(i)] = fetchFrame(window, movies(i), sources(i), 1, resources, i);
                frameIndex(i) = 1;
            end
        end
        onset = []; vbl = []; ended = false; action = '';
        skippedSamples = 0;
        while isempty(action)
            if ~ended
                if isempty(onset), elapsed = 0; else, elapsed = vbl + ifi - onset; end
                c = min(3, floor(max(0,elapsed) / 1.5) + 1);
                spec = settings{p,side}(c,:);
                f = min(round(1.5*spec(3)), ...
                    floor(max(0, elapsed - (c-1)*1.5) * spec(3) + 1e-6) + 1);
                ended = elapsed >= 4.5;
                i = lookup(side,c);
                skippedSamples = skippedSamples + max(0, f-frameIndex(i)-1);
                while frameIndex(i) < f
                    [textures(i), pts] = fetchFrame(window, movies(i), sources(i), ...
                        frameIndex(i)+1, resources, i);
                    assert(pts > lastPTS(i), 'gmad:DecodeOrder', ...
                        'Non-increasing timestamps in %s at frame %d.', sources(i), frameIndex(i)+1);
                    lastPTS(i) = pts;
                    frameIndex(i) = frameIndex(i)+1;
                end
                drawFrame(window, destination, TEXT_SIZE, textures(i), ...
                    pairs, p, side, c, spec, ended);
                if isempty(vbl)
                    vbl = Screen('Flip', window); onset = vbl;
                    fprintf('PLAY pair %d, video %c\n', p, char('A'+side-1));
                else
                    vbl = Screen('Flip', window, vbl + 0.5*ifi);
                end
                if ended
                    fprintf('FINISHED pair %d, video %c: presentation skipped samples = %d.\n', ...
                        p, char('A'+side-1), skippedSamples);
                end
            else
                WaitSecs('YieldSecs', 0.002);
            end
            action = readAction(keys);
        end
        if strcmp(action, 'quit'), return; end
        if strcmp(action, 'next')
            % Exactly black, with no labels. Next-pair loading starts only
            % after this interval; its loading screen may add a short wait.
            Screen('FillRect', window, 0); blankOnset = Screen('Flip', window);
            while GetSecs < blankOnset + BLANK_SECONDS
                if strcmp(readAction(keys), 'quit'), return; end
                WaitSecs('YieldSecs', 0.001);
            end
            fprintf('BLANK pair %d: %.3f s before next-pair loading.\n', p, GetSecs-blankOnset);
            break;
        end
        if strcmp(action, 'a'), side = 1; else, side = 2; end
    end
end
fprintf('All %d pairs completed.\n', height(pairs));
end

function drawFrame(window, destination, TEXT_SIZE, texture, pairs, pairIndex, videoSide, chunk, spec, ended)
        Screen('FillRect', window, 0);
        % Bilinear GPU scaling; frame repetition supplies native temporal
        % sampling. No optical-flow or blended-frame interpolation.
        Screen('DrawTexture', window, texture, [], destination, 0, 1);
        lines = {sprintf('Pair %d/%d  %s   Video %c', pairIndex, height(pairs), ...
            pairs.pair_id(pairIndex), char('A'+videoSide-1)), ...
            sprintf('Chunk %d/3: %d x %d | %d fps', chunk, spec(1), spec(2), spec(3)), ...
            sprintf('Linked gMAD tasks: %d', pairs.gmad_task_count(pairIndex)), ...
            'Left: A   Right: B   Enter: next   Esc: quit'};
        if ended, lines{end+1} = 'Finished - choose A/B to replay or Enter to continue.'; end
        x = destination(1)+12; y = destination(2)+12;
        labelWidth = 0;
        for line = 1:numel(lines)
            bounds = Screen('TextBounds', window, lines{line});
            labelWidth = max(labelWidth, bounds(3)-bounds(1));
        end
        Screen('FillRect', window, 0, [x-6 y-6 min(destination(3),x+labelWidth+10) ...
            y+numel(lines)*(TEXT_SIZE+7)+6]);
        for line = 1:numel(lines)
            Screen('DrawText', window, lines{line}, x, y+(line-1)*(TEXT_SIZE+7), [255 255 255]);
        end
end

function [texture, pts] = fetchFrame(window, movie, source, frame, resources, slot)
try
    [texture, pts] = Screen('GetMovieImage', window, movie, 1);
catch cause
    failure = MException('gmad:DecodeFrame', ...
        'HEVC decoding failed in %s at frame %d. See the preceding Psychtoolbox error.', source, frame);
    throw(addCause(failure, cause));
end
assert(texture > 0, 'gmad:DecodeFrames', 'Missing frame %d in %s.', frame, source);
previous = resources('textures');
oldTexture = previous(slot);
% Register the newly acquired texture before any subsequent operation fails.
resources('textures') = [previous texture];
if oldTexture > 0, Screen('Close', oldTexture); end
previous(slot) = texture;
resources('textures') = previous;
end

function action = readAction(keys)
action = '';
[pressed, ~, ~, lastPress] = KbQueueCheck;
if ~pressed, return; end
KbQueueFlush;
if lastPress(keys(4)) > 0, action = 'quit'; return; end
[time, selected] = max(lastPress(keys(1:3)));
if time > 0
    actions = {'a','b','next'}; action = actions{selected};
end
end

function cleanupResources(resources)
if resources('queueCreated'), try KbQueueRelease; catch, end, end
releasePair(resources);
window = resources('window');
if ~isempty(window) && ismember(window, liveWindows())
    try Screen('Close', window); catch, end
end
if ~isempty(window), try ShowCursor; catch, end, end
if ~isempty(resources('oldSkipSync'))
    try Screen('Preference', 'SkipSyncTests', resources('oldSkipSync')); catch, end
end
setenv('PATH', resources('oldPath'));
end

function releasePair(resources)
% Fatal Screen errors can call CloseAll internally, invalidating every
% handle before onCleanup runs. Avoid closing those handles a second time.
live = liveWindows();
window = resources('window');
if ~isempty(window) && ismember(window, live)
    movies = resources('movies');
    resources('movies') = [];
    for movie = movies(isfinite(movies))
        try Screen('CloseMovie', movie); catch, end
    end
    textures = resources('textures');
    resources('textures') = [];
    textures = textures(textures > 0 & ismember(textures, live));
    if ~isempty(textures), try Screen('Close', textures); catch, end, end
else
    resources('movies') = [];
    resources('textures') = [];
end
end

function live = liveWindows()
try live = Screen('Windows'); catch, live = []; end
end
