function results = run_dsis_gmad_480p1080p(subjectId, validateOnly, previewOnly, recipeFile, outDir, scene)
% RUN_DSIS_GMAD_480P1080P DSIS rating of gMAD-selected videos (480p-1080p).
%   run_dsis_gmad_480p1080p           % Asks for the scene, then the subject ID.
%   run_dsis_gmad_480p1080p('S01')    % Asks for the scene.
%   run_dsis_gmad_480p1080p('S01', false, false, [], [], 'bistro') % No questions.
%   plan = run_dsis_gmad_480p1080p('S01', true, false, [], [], 'bistro'); % Validate only.
%   run_dsis_gmad_480p1080p('S01', false, true, [], [], 'bistro'); % Windowed preview
%   run_dsis_gmad_480p1080p('S01', false, false, recipeFile, outDir) % Any video list
% Without a recipe file, plays one scene's videos from Version A of the
% multi-scene gMAD selection and writes to results/dsis_version_a_<scene>.
% run_dsis_version_a.m plays all of Version A. The earlier 209-video bistro
% list is gmad_bistro_480p720p1080p_.../selected_video_recipes.json.
% Each video is compared with its own shot's reference.
% Each trial: grey "Reference" card -> reference (1080p120 x 3 chunks, 4.5 s)
% -> grey "Test" card -> test video (4.5 s) -> five-level DSIS impairment
% scale (ITU-R BT.500). Frames are streamed from the HEVC chunks at their
% native 30/60/120 fps, as in play_gmad_all_resolutions.m.
% Keys: 1-5 = choose score; Enter = confirm and next; R = replay trial; Esc = quit.
% Each rating is appended to <subject>_ratings.csv as soon as it is
% confirmed. Rerunning with the same subject ID resumes in the saved order;
% a session ends after SESSION_TRIALS ratings.

%% User settings
FULL_SCREEN = true;                 % true: fullscreen; false: windowed preview
SCREEN_NUMBER = [];                 % []: highest screen number
WINDOW_RECT = [100 100 1380 820];   % 1280 x 720 window
TITLE_SECONDS = 1.0;                % grey "Reference" card before the reference
GAP_SECONDS = 1.5;                  % grey "Test" card between reference and test
GREY = 128;
BREAK_EVERY = 40;                   % rest screen every N trials (0: never)
SESSION_TRIALS = 120;               % end the session after N ratings (Inf: no limit)
TEXT_SIZE = 30;
TEXT_FONT = 'Arial';
SKIP_SYNC_TESTS = ~FULL_SCREEN;
GSTREAMER_BIN = 'C:\gstreamer\1.0\msvc_x86_64\bin';
SCALE = {5, 'Excellent - Imperceptible'
         4, 'Good - Perceptible, but not annoying'
         3, 'Fair - Slightly annoying'
         2, 'Poor - Annoying'
         1, 'Bad - Very annoying'};

if nargin < 1, subjectId = []; end
if nargin < 2, validateOnly = false; end
% Explicit preview override leaves the user's fullscreen configuration intact.
if nargin >= 3 && previewOnly
    FULL_SCREEN = false;
    SKIP_SYNC_TESTS = true;
end

workspace = fileparts(fileparts(fileparts(mfilename('fullpath'))));
resultsRoot = fullfile(workspace, 'VQA2-gmad-pooling', 'results');
pickScene = nargin < 4 || isempty(recipeFile);
if pickScene
    recipeFile = fullfile(resultsRoot, 'gmad_all_shots_480p720p1080p_skip_negative_no_offset_time_converted', ...
        'selection_all_scenes', 'video_recipes.json');
end
assert(isfile(recipeFile), 'gmad:MissingRecipes', 'Missing recipes: %s', recipeFile);
recipes = jsondecode(fileread(recipeFile));
if pickScene
    % Recipe "scene" is the shot group, e.g. forza__forza_1; the scene is its prefix.
    sceneOf = extractBefore(string({recipes.scene}) + "__", "__");
    names = unique(sceneOf);
    if nargin < 6 || isempty(scene)
        fprintf('Scenes in Version A:\n');
        for s = 1:numel(names)
            members = recipes(sceneOf == names(s));
            fprintf('  %2d  %-10s %2d videos, %d shot(s)\n', s, names(s), numel(members), ...
                numel(unique(string({members.scene}))));
        end
        scene = strtrim(input('Scene (number or name): ', 's'));
        if ~isnan(str2double(scene)) && any(str2double(scene) == 1:numel(names))
            scene = names(str2double(scene));
        end
    end
    scene = string(scene);
    assert(any(names == scene), 'gmad:Scene', 'Unknown scene "%s". Choose one of: %s.', scene, strjoin(names, ', '));
    recipes = recipes(sceneOf == scene);
    fprintf('Scene: %s (%d videos)\n', scene, numel(recipes));
    if nargin < 5 || isempty(outDir)
        outDir = fullfile(resultsRoot, "dsis_version_a_" + scene);
    end
end
assert(nargin >= 5 && ~isempty(outDir) || pickScene, 'gmad:OutDir', 'Pass outDir together with recipeFile.');
outDir = char(outDir);
if isempty(subjectId)
    % Clicking Run in the editor passes no arguments; ask in the Command Window,
    % offering the next unused number so that new subjects never reuse an ID.
    suggested = nextSubjectId(outDir);
    subjectId = strtrim(input(sprintf('Subject ID [Enter = %s, or the same ID to resume]: ', suggested), 's'));
    if isempty(subjectId), subjectId = suggested; end
end
subjectId = char(subjectId);
assert(~isempty(regexp(subjectId, '^[A-Za-z0-9_-]+$', 'once')), 'gmad:Subject', ...
    'Subject ID may contain only letters, digits, _ and -.');
n = numel(recipes);
assert(n > 0, 'gmad:InvalidRecipes', 'No selected videos in %s.', recipeFile);
ids = strings(n, 1); labels = strings(n, 3); testPaths = strings(n, 3);
shots = strings(n, 1); refPaths = strings(n, 3);
specs = zeros(n, 3, 3);
heights = [480 720 1080]; widths = [854 1280 1920];
for v = 1:n
    r = recipes(v);
    ids(v) = r.candidate_id;
    shots(v) = r.scene;
    for c = 1:3
        refPaths(v,c) = localPath(string(r.source_references{c}), workspace);
    end
    for c = 1:3
        labels(v,c) = r.(sprintf('chunk%d', c));
        token = regexp(char(labels(v,c)), '^(480|720|1080)p(30|60|120)$', 'tokens', 'once');
        assert(~isempty(token), 'gmad:WrongConditions', ...
            'This experiment expects only 480p/720p/1080p at 30/60/120 fps: %s', ids(v));
        h = str2double(token{1});
        specs(v,c,:) = [widths(heights == h), h, str2double(token{2})];
        testPaths(v,c) = localPath(string(r.source_videos{c}), workspace);
        % 1080p120 is the reference itself. Use the reference file (same
        % pixels, corrected last packet duration), as the pair player does.
        if labels(v,c) == "1080p120", testPaths(v,c) = refPaths(v,c); end
        assert(isfile(testPaths(v,c)), 'gmad:MissingChunk', 'Missing HEVC chunk: %s', testPaths(v,c));
        assert(isfile(refPaths(v,c)), 'gmad:MissingChunk', 'Missing reference chunk: %s', refPaths(v,c));
    end
    assert(ids(v) == shots(v) + "__" + strjoin(labels(v,:), '-'), ...
        'gmad:SettingsMismatch', 'Candidate identifier and settings disagree: %s', ids(v));
end
assert(numel(unique(ids)) == n, 'gmad:InvalidRecipes', 'Expected unique candidate IDs.');
% One reference per shot, so the reference shown always matches the test content.
[shotNames, ~, shotIndex] = unique(shots);
for s = 1:numel(shotNames)
    assert(size(unique(refPaths(shotIndex == s, :), 'rows'), 1) == 1, 'gmad:InvalidRecipes', ...
        'Shot %s uses more than one reference.', shotNames(s));
end
plan = table(ids, shots, labels(:,1), labels(:,2), labels(:,3), ...
    'VariableNames', {'candidate_id', 'shot', 'chunk1', 'chunk2', 'chunk3'});
fprintf('Validated %d gMAD-selected videos from %d shots / %d HEVC test chunks + %d reference chunks.\n', ...
    n, numel(shotNames), numel(unique(testPaths(:))), numel(unique(refPaths(:))));
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
    seed = double(saved.seed(1));
else
    stream = RandStream('mt19937ar', 'Seed', 'shuffle');
    order = ids(randperm(stream, n));
    seed = double(stream.Seed);
    writetable(table((1:n)', order, repmat(seed, n, 1), ...
        'VariableNames', {'trial', 'candidate_id', 'seed'}), orderFile);
end
[~, videoIndex] = ismember(order, ids);
done = strings(0, 1);
if isfile(ratingFile)
    % Ratings written before the seed column existed get it inserted after "subject".
    lines = readlines(ratingFile);
    lines = lines(strlength(lines) > 0);
    if ~startsWith(lines(1), "subject,seed,")
        lines(1) = replace(lines(1), "subject,", "subject,seed,");
        lines(2:end) = extractBefore(lines(2:end), ",") + "," + sprintf('%d', seed) + "," + extractAfter(lines(2:end), ",");
        writelines(lines, ratingFile);
    end
    previous = readtable(ratingFile, 'TextType', 'string', 'Delimiter', ',');
    if height(previous) > 0, done = previous.candidate_id; end
else
    fid = fopen(ratingFile, 'w');
    fprintf(fid, ['subject,seed,trial,candidate_id,chunk1,chunk2,chunk3,score,replays,' ...
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
sessionEnd = remaining(min(end, SESSION_TRIALS));
remaining = remaining(1:min(end, SESSION_TRIALS));

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

refSpecs = repmat([1920 1080 120], 3, 1);
loadedShot = "";

drawScale(window, GREY, SCALE, 0, ...
    {'Each trial shows the REFERENCE video, then the TEST video (4.5 s each).', ...
     'Rate the impairment of the TEST video compared with the REFERENCE:'}, ...
    {'Press Enter to start'});
Screen('Flip', window);
if ~waitForEnter(keys), return; end

%% Trials
for k = remaining
    v = videoIndex(k);
    if BREAK_EVERY > 0 && k ~= remaining(1) && mod(k-1, BREAK_EVERY) == 0
        showMessage(window, GREY, {sprintf('Break: %d / %d done.', k-1, n), '', 'Press Enter to continue'});
        if ~waitForEnter(keys), return; end
    end
    showMessage(window, GREY, {'Loading...'});
    % Reference decoders stay open while consecutive trials share a shot.
    if shots(v) ~= loadedShot
        closeSlots(resources, 1:3);
        for c = 1:3
            openMovie(window, resources, c, refPaths(v,c), refSpecs(c,:));
        end
        loadedShot = shots(v);
    end
    closeSlots(resources, 4:6);
    for c = 1:3
        openMovie(window, resources, 3 + c, testPaths(v,c), squeeze(specs(v,c,:))');
    end
    fprintf('TRIAL %d/%d: %s\n', k, n, ids(v));
    replays = 0;
    while true
        [vbl, refSkipped, quit] = playClip(window, resources, 1:3, refSpecs, refPaths(v,:), ...
            {'Reference'}, 0, TITLE_SECONDS, destination, ifi, keys, GREY);
        if quit, return; end
        [vbl, testSkipped, quit] = playClip(window, resources, 4:6, squeeze(specs(v,:,:)), testPaths(v,:), ...
            {'Test'}, vbl + 0.5*ifi, GAP_SECONDS, destination, ifi, keys, GREY);
        if quit, return; end
        [score, action, ratingTime] = rateVideo(window, GREY, SCALE, keys, vbl + 0.5*ifi, ...
            {sprintf('Trial %d / %d', k, n), ...
             '1-5: choose   Enter: confirm   R: replay'});
        if strcmp(action, 'quit'), return; end
        if strcmp(action, 'next'), break; end
        replays = replays + 1;
    end
    fid = fopen(ratingFile, 'a');
    fprintf(fid, '%s,%d,%d,%s,%s,%s,%s,%d,%d,%.3f,%d,%d,%s\n', subjectId, seed, k, ids(v), ...
        labels(v,1), labels(v,2), labels(v,3), ...
        score, replays, ratingTime, refSkipped, testSkipped, ...
        char(datetime('now', 'Format', 'yyyy-MM-dd''T''HH:mm:ss')));
    fclose(fid);
    fprintf('  score=%d, replays=%d, skipped samples ref/test=%d/%d\n', ...
        score, replays, refSkipped, testSkipped);
end
results = readtable(ratingFile, 'TextType', 'string');
if height(results) < n
    showMessage(window, GREY, {sprintf('Session finished: %d / %d done. Thank you!', height(results), n)});
    WaitSecs(2);
    fprintf('Session ended after trial %d: %d/%d rated. Rerun with the same subject ID to continue.\n', ...
        sessionEnd, height(results), n);
    return;
end
showMessage(window, GREY, {'Finished. Thank you!'});
WaitSecs(2);
fprintf('All %d videos rated. Ratings: %s\n', n, ratingFile);
end

function path = localPath(path, workspace)
% Recipes store absolute paths from the machine that made them. When a path is
% missing here, look for the same file under this workspace's VQA2-dataset,
% so any <root>/VQA2-gmad-pooling + <root>/VQA2-dataset layout works.
if isfile(path), return; end
relative = regexp(char(path), '[\\/]VQA2-dataset[\\/](.*)$', 'tokens', 'once');
if ~isempty(relative)
    candidate = string(fullfile(workspace, 'VQA2-dataset', strrep(relative{1}, '/', filesep)));
    if isfile(candidate), path = candidate; end
end
end

function id = nextSubjectId(outDir)
% Next unused "S<NN>_<yyyymmdd>" ID, numbering past every S<NN> already in outDir.
used = 0;
listing = dir(fullfile(outDir, 'S*_order.csv'));
for file = listing'
    token = regexp(file.name, '^S(\d+)', 'tokens', 'once');
    if ~isempty(token), used = max(used, str2double(token{1})); end
end
id = sprintf('S%02d_%s', used + 1, char(datetime('now', 'Format', 'yyyyMMdd')));
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
header = {'Rate the impairment of the TEST video compared with the REFERENCE'};
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
% Five DSIS levels as aligned columns: score, label.
Screen('FillRect', window, grey);
[width, height] = Screen('WindowSize', window);
rowHeight = round(Screen('TextSize', window) * 1.8);
labelWidth = max(cellfun(@(text) textWidth(window, text), scale(:,2)));
numberWidth = textWidth(window, '5'); gap = rowHeight;
x = (width - (numberWidth + labelWidth + gap)) / 2;
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
