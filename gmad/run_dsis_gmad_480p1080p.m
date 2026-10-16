function results = run_dsis_gmad_480p1080p(subjectId, validateOnly, previewOnly)
% RUN_DSIS_GMAD_480P1080P DSIS rating of gMAD-selected bistro videos (480p-1080p).
%   run_dsis_gmad_480p1080p('S01')
%   plan = run_dsis_gmad_480p1080p('S01', true); % Validate without opening a window.
%   run_dsis_gmad_480p1080p('S01', false, true); % Windowed preview if fullscreen sync fails
% Each trial: grey "Reference" card -> reference (1080p120 x 3 chunks, 4.5 s)
% -> grey "Test" card -> test video (4.5 s) -> five-level DSIS impairment
% scale (ITU-R BT.500). Frames are streamed from the HEVC chunks at their
% native 30/60/120 fps, as in play_gmad_all_resolutions.m.
% Keys: 1-5 = choose score; Enter = confirm and next; R = replay trial; Esc = quit.
% Each rating is appended to <subject>_ratings.csv as soon as it is
% confirmed. Rerunning with the same subject ID resumes in the saved order.

%% User settings
FULL_SCREEN = true;                 % true: fullscreen; false: windowed preview
SCREEN_NUMBER = [];                 % []: highest screen number
WINDOW_RECT = [100 100 1380 820];   % 1280 x 720 window
TITLE_SECONDS = 1.0;                % grey "Reference" card before the reference
GAP_SECONDS = 1.5;                  % grey "Test" card between reference and test
GREY = 128;
BREAK_EVERY = 40;                   % rest screen every N trials (0: never)
TEXT_SIZE = 30;
TEXT_FONT = 'Microsoft YaHei';      % needs CJK glyphs for the Chinese labels
SKIP_SYNC_TESTS = ~FULL_SCREEN;
GSTREAMER_BIN = 'C:\gstreamer\1.0\msvc_x86_64\bin';
SCALE = {5, 'Excellent - Imperceptible',            '无法察觉'
         4, 'Good - Perceptible, but not annoying', '可察觉，但不恼人'
         3, 'Fair - Slightly annoying',             '轻微恼人'
         2, 'Poor - Annoying',                      '恼人'
         1, 'Bad - Very annoying',                  '非常恼人'};

if nargin < 1 || isempty(subjectId)
    error('gmad:Subject', 'Usage: run_dsis_gmad_480p1080p(''S01'')');
end
subjectId = char(subjectId);
assert(~isempty(regexp(subjectId, '^[A-Za-z0-9_-]+$', 'once')), 'gmad:Subject', ...
    'Subject ID may contain only letters, digits, _ and -.');
if nargin < 2, validateOnly = false; end
% Explicit preview override leaves the user's fullscreen configuration intact.
if nargin >= 3 && previewOnly
    FULL_SCREEN = false;
    SKIP_SYNC_TESTS = true;
end

workspace = fileparts(fileparts(fileparts(mfilename('fullpath'))));
resultsRoot = fullfile(workspace, 'VQA2-gmad-pooling', 'results');
recipeFile = fullfile(resultsRoot, 'gmad_bistro_480p720p1080p_skip_negative_no_offset_time_converted', ...
    'selected_video_recipes.json');
outDir = fullfile(resultsRoot, 'dsis_bistro_480p720p1080p');
assert(isfile(recipeFile), 'gmad:MissingRecipes', 'Missing recipes: %s', recipeFile);
recipes = jsondecode(fileread(recipeFile));
n = numel(recipes);
assert(n > 0, 'gmad:InvalidRecipes', 'No selected videos in %s.', recipeFile);
refPaths = string(recipes(1).source_references(:))';
ids = strings(n, 1); labels = strings(n, 3); testPaths = strings(n, 3);
specs = zeros(n, 3, 3);
heights = [480 720 1080]; widths = [854 1280 1920];
for v = 1:n
    r = recipes(v);
    ids(v) = r.candidate_id;
    assert(string(r.scene) == "bistro" && isequal(string(r.source_references(:))', refPaths), ...
        'gmad:InvalidRecipes', 'Expected bistro videos sharing one reference: %s', ids(v));
    for c = 1:3
        labels(v,c) = r.(sprintf('chunk%d', c));
        token = regexp(char(labels(v,c)), '^(480|720|1080)p(30|60|120)$', 'tokens', 'once');
        assert(~isempty(token), 'gmad:WrongConditions', ...
            'This experiment expects only 480p/720p/1080p at 30/60/120 fps: %s', ids(v));
        h = str2double(token{1});
        specs(v,c,:) = [widths(heights == h), h, str2double(token{2})];
        testPaths(v,c) = r.source_videos{c};
        % 1080p120 is the reference itself. Use the reference file (same
        % pixels, corrected last packet duration), as the pair player does.
        if labels(v,c) == "1080p120", testPaths(v,c) = refPaths(c); end
        assert(isfile(testPaths(v,c)), 'gmad:MissingChunk', 'Missing HEVC chunk: %s', testPaths(v,c));
    end
    assert(ids(v) == "bistro__" + strjoin(labels(v,:), '-'), ...
        'gmad:SettingsMismatch', 'Candidate identifier and settings disagree: %s', ids(v));
end
assert(numel(unique(ids)) == n, 'gmad:InvalidRecipes', 'Expected unique candidate IDs.');
for c = 1:3
    assert(isfile(refPaths(c)), 'gmad:MissingChunk', 'Missing reference chunk: %s', refPaths(c));
end
plan = table(ids, labels(:,1), labels(:,2), labels(:,3), ...
    'VariableNames', {'candidate_id', 'chunk1', 'chunk2', 'chunk3'});
fprintf('Validated %d gMAD-selected videos / %d HEVC test chunks + 3 reference chunks.\n', ...
    n, numel(unique(testPaths(:))));
fprintf('Recipes: %s\n', recipeFile);
results = plan;
if validateOnly, return; end
assert(exist('Screen', 'file') ~= 0, 'gmad:MissingPsychtoolbox', 'Psychtoolbox is not on the MATLAB path.');

%% Presentation order and resume state
if ~isfolder(outDir), mkdir(outDir); end
orderFile = fullfile(outDir, [subjectId '_order.csv']);
ratingFile = fullfile(outDir, [subjectId '_ratings.csv']);
if isfile(orderFile)
    saved = readtable(orderFile, 'TextType', 'string');
    assert(height(saved) == n && isequal(sort(saved.candidate_id), sort(ids)), 'gmad:OrderMismatch', ...
        'Saved order %s does not match the current recipes.', orderFile);
    order = saved.candidate_id;
else
    stream = RandStream('mt19937ar', 'Seed', 'shuffle');
    order = ids(randperm(stream, n));
    writetable(table((1:n)', order, repmat(stream.Seed, n, 1), ...
        'VariableNames', {'trial', 'candidate_id', 'seed'}), orderFile);
end
[~, videoIndex] = ismember(order, ids);
done = strings(0, 1);
if isfile(ratingFile)
    previous = readtable(ratingFile, 'TextType', 'string', 'Delimiter', ',');
    if height(previous) > 0, done = previous.candidate_id; end
else
    fid = fopen(ratingFile, 'w');
    fprintf(fid, ['subject,trial,candidate_id,chunk1,chunk2,chunk3,score,replays,' ...
        'rating_time_s,reference_skipped_samples,test_skipped_samples,timestamp\n']);
    fclose(fid);
end
remaining = find(~ismember(order, done))';
fprintf('Subject %s: %d/%d rated; %d remaining. Ratings: %s\n', ...
    subjectId, n - numel(remaining), n, numel(remaining), ratingFile);
if isempty(remaining)
    results = readtable(ratingFile, 'TextType', 'string');
    return;
end

%% Psychtoolbox setup
% A handle map makes resource cleanup safe during errors and Ctrl+C.
% Movie/texture slots 1-3 hold the reference chunks, 4-6 the test chunks.
resources = containers.Map('KeyType', 'char', 'ValueType', 'any');
resources('window') = []; resources('movies') = nan(1, 6);
resources('textures') = zeros(1, 6); resources('queueCreated') = false;
resources('oldSkipSync') = []; resources('oldPath') = getenv('PATH');
cleanupGuard = onCleanup(@() cleanupResources(resources));
if ~isempty(GSTREAMER_BIN)
    assert(isfolder(GSTREAMER_BIN), 'gmad:MissingGStreamer', 'Missing GSTREAMER_BIN.');
    setenv('PATH', [GSTREAMER_BIN pathsep resources('oldPath')]);
end
KbName('UnifyKeyNames');
keys = [KbName({'1!', '2@', '3#', '4$', '5%'}), KbName('Return'), KbName('r'), KbName('ESCAPE')];
keyList = zeros(1, 256); keyList(keys) = 1;
resources('oldSkipSync') = Screen('Preference', 'SkipSyncTests', double(SKIP_SYNC_TESTS));
screens = Screen('Screens');
if isempty(SCREEN_NUMBER), SCREEN_NUMBER = max(screens); end
assert(ismember(SCREEN_NUMBER, screens), 'gmad:ScreenNumber', 'Requested screen unavailable.');
if FULL_SCREEN
    [window, rect] = Screen('OpenWindow', SCREEN_NUMBER, GREY);
else
    [window, rect] = Screen('OpenWindow', SCREEN_NUMBER, GREY, WINDOW_RECT);
end
resources('window') = window;
HideCursor;
Screen('TextFont', window, TEXT_FONT); Screen('TextSize', window, TEXT_SIZE);
ifi = Screen('GetFlipInterval', window);
fprintf('Display refresh: %.2f Hz. Native frames held at 30 / 60 / 120 fps.\n', 1/ifi);
fprintf('1-5=score; Enter=confirm; R=replay; Escape=quit.\n');
KbQueueCreate([], keyList); resources('queueCreated') = true; KbQueueStart;
windowSize = rect(3:4) - rect(1:2);
drawSize = [1920 1080] * min(windowSize ./ [1920 1080]);
origin = (windowSize - drawSize) / 2;
destination = [origin origin + drawSize];

showMessage(window, GREY, {'Loading reference video...', '正在加载参考视频...'});
for c = 1:3
    openMovie(window, resources, c, refPaths(c), [1920 1080 120]);
end
refSpecs = repmat([1920 1080 120], 3, 1);

drawScale(window, GREY, SCALE, 0, ...
    {'Each trial shows the REFERENCE video, then the TEST video (4.5 s each).', ...
     '每组先播放参考视频，再播放测试视频（各 4.5 秒）。', ...
     'Rate the impairment of the TEST video compared with the REFERENCE:', ...
     '请根据测试视频相对参考视频的损伤程度打分：'}, ...
    {'Press Enter to start   |   按 Enter 开始'});
Screen('Flip', window);
if ~waitForEnter(keys), return; end

%% Trials
for k = remaining
    v = videoIndex(k);
    if BREAK_EVERY > 0 && k ~= remaining(1) && mod(k-1, BREAK_EVERY) == 0
        showMessage(window, GREY, {sprintf('Break: %d / %d done.', k-1, n), ...
            sprintf('休息一下：已完成 %d / %d。', k-1, n), '', 'Press Enter to continue   |   按 Enter 继续'});
        if ~waitForEnter(keys), return; end
    end
    showMessage(window, GREY, {'Loading...', '正在加载...'});
    closeSlots(resources, 4:6);
    for c = 1:3
        openMovie(window, resources, 3 + c, testPaths(v,c), squeeze(specs(v,c,:))');
    end
    fprintf('TRIAL %d/%d: %s\n', k, n, ids(v));
    replays = 0;
    while true
        [vbl, refSkipped, quit] = playClip(window, resources, 1:3, refSpecs, refPaths, ...
            {'Reference', '参考视频'}, 0, TITLE_SECONDS, destination, ifi, keys, GREY);
        if quit, return; end
        [vbl, testSkipped, quit] = playClip(window, resources, 4:6, squeeze(specs(v,:,:)), testPaths(v,:), ...
            {'Test', '测试视频'}, vbl + 0.5*ifi, GAP_SECONDS, destination, ifi, keys, GREY);
        if quit, return; end
        [score, action, ratingTime] = rateVideo(window, GREY, SCALE, keys, vbl + 0.5*ifi, ...
            {sprintf('Trial %d / %d', k, n), ...
             '1-5: choose   Enter: confirm   R: replay   |   1-5：选择   Enter：确认   R：重播'});
        if strcmp(action, 'quit'), return; end
        if strcmp(action, 'next'), break; end
        replays = replays + 1;
    end
    fid = fopen(ratingFile, 'a');
    fprintf(fid, '%s,%d,%s,%s,%s,%s,%d,%d,%.3f,%d,%d,%s\n', subjectId, k, ids(v), ...
        labels(v,1), labels(v,2), labels(v,3), ...
        score, replays, ratingTime, refSkipped, testSkipped, ...
        char(datetime('now', 'Format', 'yyyy-MM-dd''T''HH:mm:ss')));
    fclose(fid);
    fprintf('  score=%d, replays=%d, skipped samples ref/test=%d/%d\n', ...
        score, replays, refSkipped, testSkipped);
end
showMessage(window, GREY, {'Finished. Thank you!', '实验结束，谢谢！'});
WaitSecs(2);
results = readtable(ratingFile, 'TextType', 'string');
fprintf('All %d videos rated. Ratings: %s\n', n, ratingFile);
end

function [vbl, skipped, quit] = playClip(window, resources, slots, chunkSpecs, sources, card, when, cardSeconds, destination, ifi, keys, grey)
% Grey title card, then three consecutive 1.5 s chunks. Decoders rewind
% during the card, so preparation does not lengthen the inter-clip gap.
quit = false; skipped = 0;
Screen('FillRect', window, grey);
drawLines(window, card, 255);
cardOnset = Screen('Flip', window, when);
movies = resources('movies');
frameIndex = ones(1, 3); lastPTS = -inf(1, 3);
for c = 1:3
    Screen('SetMovieTimeIndex', movies(slots(c)), 0);
    [~, lastPTS(c)] = fetchFrame(window, movies(slots(c)), sources(c), 1, resources, slots(c));
end
onset = []; vbl = [];
while true
    if isempty(onset), elapsed = 0; else, elapsed = vbl + ifi - onset; end
    if elapsed > 4.5 - 0.5*ifi, break; end
    c = min(3, floor(max(0, elapsed) / 1.5) + 1);
    fps = chunkSpecs(c,3);
    f = min(round(1.5*fps), floor(max(0, elapsed - (c-1)*1.5) * fps + 1e-6) + 1);
    skipped = skipped + max(0, f-frameIndex(c)-1);
    while frameIndex(c) < f
        [~, pts] = fetchFrame(window, movies(slots(c)), sources(c), frameIndex(c)+1, resources, slots(c));
        assert(pts > lastPTS(c), 'gmad:DecodeOrder', ...
            'Non-increasing timestamps in %s at frame %d.', sources(c), frameIndex(c)+1);
        lastPTS(c) = pts;
        frameIndex(c) = frameIndex(c)+1;
    end
    textures = resources('textures');
    Screen('FillRect', window, 0);
    % Bilinear GPU scaling; frame repetition supplies native temporal
    % sampling. No optical-flow or blended-frame interpolation.
    Screen('DrawTexture', window, textures(slots(c)), [], destination, 0, 1);
    if isempty(onset)
        vbl = Screen('Flip', window, cardOnset + cardSeconds - 0.5*ifi); onset = vbl;
    else
        vbl = Screen('Flip', window, vbl + 0.5*ifi);
    end
    if strcmp(readKey(keys), 'quit'), quit = true; return; end
end
end

function [score, action, ratingTime] = rateVideo(window, grey, scale, keys, when, footer)
score = 0; action = '';
KbQueueFlush;
header = {'Rate the impairment of the TEST video compared with the REFERENCE', ...
    '请评价测试视频相对参考视频的损伤程度'};
drawScale(window, grey, scale, score, header, footer);
onset = Screen('Flip', window, when);
while isempty(action)
    key = readKey(keys);
    switch key
        case {'1', '2', '3', '4', '5'}
            score = str2double(key);
            drawScale(window, grey, scale, score, header, footer);
            Screen('Flip', window);
        case 'enter'
            if score > 0, action = 'next'; end
        case {'replay', 'quit'}
            action = key;
        otherwise
            WaitSecs('YieldSecs', 0.005);
    end
end
ratingTime = GetSecs - onset;
end

function drawScale(window, grey, scale, score, header, footer)
% Five DSIS levels as aligned columns: score, English label, Chinese label.
Screen('FillRect', window, grey);
[width, height] = Screen('WindowSize', window);
rowHeight = round(Screen('TextSize', window) * 1.8);
columnWidth = @(column) max(cellfun(@(text) textWidth(window, text), scale(:,column)));
numberWidth = textWidth(window, '5'); gap = rowHeight;
x = (width - (numberWidth + columnWidth(2) + columnWidth(3) + 2*gap)) / 2;
top = (height - (numel(header) + size(scale, 1) + numel(footer) + 2) * rowHeight) / 2;
drawLines(window, header, 255, top, rowHeight);
for row = 1:size(scale, 1)
    y = top + (numel(header) + row) * rowHeight;
    if scale{row,1} == score
        Screen('FillRect', window, [40 90 170], ...
            [x-gap/2, y-rowHeight*0.2, width-x+gap/2, y+rowHeight*0.85]);
    end
    Screen('DrawText', window, double(num2str(scale{row,1})), x, y, 255);
    Screen('DrawText', window, double(scale{row,2}), x + numberWidth + gap, y, 255);
    Screen('DrawText', window, double(scale{row,3}), x + numberWidth + columnWidth(2) + 2*gap, y, 255);
end
drawLines(window, footer, 220, top + (numel(header) + size(scale, 1) + 2) * rowHeight, rowHeight);
end

function showMessage(window, grey, lines)
Screen('FillRect', window, grey);
drawLines(window, lines, 255);
Screen('Flip', window);
end

function drawLines(window, lines, color, top, rowHeight)
% Horizontally centred lines; vertically centred when TOP is omitted.
[width, height] = Screen('WindowSize', window);
if nargin < 5, rowHeight = round(Screen('TextSize', window) * 1.6); end
if nargin < 4, top = (height - numel(lines) * rowHeight) / 2; end
for line = 1:numel(lines)
    Screen('DrawText', window, double(lines{line}), (width - textWidth(window, lines{line})) / 2, ...
        top + (line-1) * rowHeight, color);
end
end

function w = textWidth(window, text)
bounds = Screen('TextBounds', window, double(text));
w = bounds(3) - bounds(1);
end

function ok = waitForEnter(keys)
KbQueueFlush;
while true
    key = readKey(keys);
    if any(strcmp(key, {'enter', 'quit'})), ok = strcmp(key, 'enter'); return; end
    WaitSecs('YieldSecs', 0.005);
end
end

function openMovie(window, resources, slot, source, spec)
[movie, duration, fps, w, h] = Screen('OpenMovie', window, char(source), 0, 1);
movies = resources('movies'); movies(slot) = movie; resources('movies') = movies;
assert(w == spec(1) && h == spec(2) && abs(fps-spec(3)) < 1 && abs(duration-1.5) < 0.02, ...
    'gmad:MovieFormat', 'Unexpected movie properties: %s', source);
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

function key = readKey(keys)
% keys = [1 2 3 4 5 Return R Escape]; Escape wins over simultaneous keys.
key = '';
[pressed, ~, ~, lastPress] = KbQueueCheck;
if ~pressed, return; end
KbQueueFlush;
if lastPress(keys(8)) > 0, key = 'quit'; return; end
[time, selected] = max(lastPress(keys(1:7)));
if time > 0
    names = {'1', '2', '3', '4', '5', 'enter', 'replay'}; key = names{selected};
end
end

function cleanupResources(resources)
if resources('queueCreated'), try KbQueueRelease; catch, end, end
closeSlots(resources, 1:numel(resources('textures')));
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

function closeSlots(resources, slots)
% Fatal Screen errors can call CloseAll internally, invalidating every
% handle before onCleanup runs. Avoid closing those handles a second time.
live = liveWindows();
window = resources('window');
movies = resources('movies'); textures = resources('textures');
movieSlots = slots(slots <= numel(movies));
if ~isempty(window) && ismember(window, live)
    for movie = movies(movieSlots(isfinite(movies(movieSlots))))
        try Screen('CloseMovie', movie); catch, end
    end
    open = textures(slots(textures(slots) > 0 & ismember(textures(slots), live)));
    if ~isempty(open), try Screen('Close', open); catch, end, end
end
movies(movieSlots) = nan; textures(slots) = 0;
resources('movies') = movies; resources('textures') = textures;
end

function live = liveWindows()
try live = Screen('Windows'); catch, live = []; end
end
