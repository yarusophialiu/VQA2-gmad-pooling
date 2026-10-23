function results = run_dsis_gmad_480p1080p(subjectId, validateOnly, previewOnly, recipeFile, outDir, scene, fixedOrder)
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
% scale (ITU-R BT.500). Every frame of each HEVC chunk is decoded into a GPU
% texture before its trial, then shown at its native 30/60/120 fps, so no
% decoding runs during playback. The next trial decodes while the rating
% screen waits for keys; any remainder finishes behind "Loading...".
% Keys: 1-5 = choose score; Enter = confirm and next; R = replay trial; Esc = quit.
% <subject>_ratings.csv holds the whole session: one row per trial in
% presentation order, written at the start with blank ratings, each row
% filled in as soon as its rating is confirmed. Rerunning with the same
% subject ID resumes at the first unrated trial; a session ends after
% SESSION_TRIALS ratings. fixedOrder = true plays the recipes in file order
% (training) instead of a random order per subject.

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
SHOW_CHUNK_INFO = false;            % true: overlay current chunk resolution/fps top-left (debug only)
SHOW_EXPECTED_LEVEL = false;        % training recipes only: show the expected DSIS level top-left during the test video
LOG_FLIP_TIMING = false;            % true: save per-flip timing of every clip to <outDir>/flip_timing (plot_flip_timing.m)
SKIP_SYNC_TESTS = ~FULL_SCREEN;
% GSTREAMER_BIN = 'C:\gstreamer\1.0\msvc_x86_64\bin';
GSTREAMER_BIN = '';
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
% Training recipes carry expected_level, shown as feedback after each rating.
expected = nan(n, 1);
specs = zeros(n, 3, 3);
heights = [480 720 1080]; widths = [854 1280 1920];
for v = 1:n
    r = recipes(v);
    ids(v) = r.candidate_id;
    shots(v) = r.scene;
    if isfield(r, 'expected_level'), expected(v) = r.expected_level; end
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

%% Session file: presentation order and ratings in one table
if ~isfolder(outDir), mkdir(outDir); end
ratingFile = fullfile(outDir, [subjectId '_ratings.csv']);
assert(~isfile(fullfile(outDir, [subjectId '_order.csv'])), 'gmad:OldSession', ...
    ['%s was started with a separate _order.csv file, which this version no longer reads. ' ...
     'Use a new subject ID, or move that subject''s files away.'], subjectId);
if isfile(ratingFile)
    session = sortrows(readSession(ratingFile), 'trial');
    assert(height(session) == n && isequal(sort(session.candidate_id), sort(ids)), 'gmad:OrderMismatch', ...
        'Saved session %s does not match the current recipes.', ratingFile);
else
    if nargin >= 7 && fixedOrder
        order = ids; seed = 0;
    else
        stream = RandStream('mt19937ar', 'Seed', 'shuffle');
        order = ids(randperm(stream, n)); seed = double(stream.Seed);
    end
    [~, idx] = ismember(order, ids);
    blank = nan(n, 1);
    session = table(repmat(string(subjectId), n, 1), repmat(seed, n, 1), (1:n)', order, ...
        labels(idx,1), labels(idx,2), labels(idx,3), blank, blank, blank, blank, blank, strings(n, 1), ...
        'VariableNames', {'subject', 'seed', 'trial', 'candidate_id', 'chunk1', 'chunk2', 'chunk3', ...
        'score', 'replays', 'rating_time_s', 'reference_skipped_samples', 'test_skipped_samples', 'timestamp'});
    writeSession(session, ratingFile);
end
[~, videoIndex] = ismember(session.candidate_id, ids);
remaining = find(isnan(session.score))';
fprintf('Subject %s: %d/%d rated; %d remaining. Session file: %s\n', ...
    subjectId, n - numel(remaining), n, numel(remaining), ratingFile);
if isempty(remaining)
    results = session;
    return;
end
sessionEnd = remaining(min(end, SESSION_TRIALS));
remaining = remaining(1:min(end, SESSION_TRIALS));

%% Psychtoolbox setup
% A handle map makes resource cleanup safe during errors and Ctrl+C.
% Slots 1-3 hold the reference chunks, 4-6 the test chunks; slots 7-12 the
% next trial's while it loads. frames{slot} are the chunk's decoded textures,
% pts{slot} their presentation timestamps, jobs the chunks still to decode.
resources = containers.Map('KeyType', 'char', 'ValueType', 'any');
resources('window') = []; resources('movies') = nan(1, 12);
resources('frames') = cell(1, 12); resources('pts') = cell(1, 12); resources('queueCreated') = false;
resources('jobs') = struct('slot', {}, 'source', {}, 'spec', {});
resources('oldSkipSync') = []; resources('oldPath') = getenv('PATH');
cleanupGuard = onCleanup(@() cleanupResources(resources));
if ~isempty(GSTREAMER_BIN)
    assert(isfolder(GSTREAMER_BIN), 'gmad:MissingGStreamer', 'Missing GSTREAMER_BIN.');
    setenv('PATH', [GSTREAMER_BIN pathsep resources('oldPath')]);
end
KbName('UnifyKeyNames');
% On Linux KbName('Return') also returns keypad Enter; keep one code so key positions stay fixed.
returnKey = KbName('Return');
keys = [KbName({'1!', '2@', '3#', '4$', '5%'}), returnKey(1), KbName('r'), KbName('ESCAPE')];
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
% Native 1920x1080, centred on black; never enlarged, only shrunk to fit a smaller window.
drawSize = [1920 1080] * min([1, windowSize ./ [1920 1080]]);
origin = (windowSize - drawSize) / 2;
destination = [origin origin + drawSize];

refSpecs = repmat([1920 1080 120], 3, 1);
loadedShot = "";
queuedTrial = 0; queuedRef = false;
% Called while screens wait for keys: decodes ~10 ms of queued frames per call.
loadWhileIdle = @() stepLoader(window, resources, 0.01);

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
        if ~waitForEnter(keys, loadWhileIdle), return; end
    end
    % Usually queued during the previous rating screen; whatever is left
    % finishes here. Reference frames stay loaded while consecutive trials
    % share a shot.
    loadStart = GetSecs;
    if queuedTrial ~= k
        queuedRef = shots(v) ~= loadedShot;
        queueTrial(resources, queuedRef, refPaths(v,:), refSpecs, testPaths(v,:), squeeze(specs(v,:,:)));
    end
    if ~isempty(resources('jobs')), showMessage(window, GREY, {'Loading...'}); end
    while ~stepLoader(window, resources, 0.1), end
    if queuedRef, promoteSlots(resources, 1:3); loadedShot = shots(v); end
    promoteSlots(resources, 4:6);
    % 1080p120 test chunks are the reference file: reuse its frames.
    testSlots = 4:6;
    sameAsRef = testPaths(v,:) == refPaths(v,:);
    testSlots(sameAsRef) = find(sameAsRef);
    fprintf('TRIAL %d/%d: %s (waited %.1f s for loading)\n', k, n, ids(v), GetSecs - loadStart);
    % Queue the next trial; it decodes while this trial's rating screen waits.
    queuedTrial = 0;
    following = remaining(find(remaining == k) + 1:end);
    if ~isempty(following)
        queuedTrial = following(1);
        next = videoIndex(queuedTrial);
        queuedRef = shots(next) ~= shots(v);
        queueTrial(resources, queuedRef, refPaths(next,:), refSpecs, testPaths(next,:), squeeze(specs(next,:,:)));
    end
    replays = 0;
    levelText = '';
    if SHOW_EXPECTED_LEVEL && ~isnan(expected(v))
        levelText = ['Expected: ' expectedRange(expected(v), SCALE)];
    end
    while true
        % An open decoder keeps decoding ahead on its own; never let one run during playback.
        suspendLoader(resources);
        [vbl, refSkipped, quit, refLog] = playClip(window, resources, 1:3, refSpecs, ...
            {'Reference'}, 0, TITLE_SECONDS, destination, ifi, keys, GREY, SHOW_CHUNK_INFO, '');
        if quit, return; end
        [vbl, testSkipped, quit, testLog] = playClip(window, resources, testSlots, squeeze(specs(v,:,:)), ...
            {'Test'}, vbl + 0.5*ifi, GAP_SECONDS, destination, ifi, keys, GREY, SHOW_CHUNK_INFO, levelText);
        if quit, return; end
        if LOG_FLIP_TIMING
            % Written after both clips, so file I/O never runs during playback.
            stem = sprintf('%s_trial%03d_play%d', subjectId, k, replays + 1);
            writeFlipLog(outDir, [stem '_reference'], refLog, refSpecs, ifi);
            writeFlipLog(outDir, [stem '_test_' char(strjoin(labels(v,:), '-'))], testLog, squeeze(specs(v,:,:)), ifi);
        end
        [score, action, ratingTime] = rateVideo(window, GREY, SCALE, keys, vbl + 0.5*ifi, ...
            {sprintf('Trial %d / %d', k, n), ...
             '1-5: choose   Enter: confirm   R: replay'}, loadWhileIdle, (k - 1) / n);
        if strcmp(action, 'quit'), return; end
        if strcmp(action, 'next'), break; end
        replays = replays + 1;
    end
    session{k, {'score', 'replays', 'rating_time_s', 'reference_skipped_samples', 'test_skipped_samples'}} = ...
        [score, replays, round(ratingTime, 3), refSkipped, testSkipped];
    session.timestamp(k) = string(datetime('now', 'Format', 'yyyy-MM-dd''T''HH:mm:ss'));
    writeSession(session, ratingFile);
    fprintf('  score=%d, replays=%d, skipped samples ref/test=%d/%d\n', ...
        score, replays, refSkipped, testSkipped);
    if ~isnan(expected(v))
        showMessage(window, GREY, {sprintf('Your rating: %d', score), ...
            ['Expected for this example: ' expectedRange(expected(v), SCALE)], '', 'Press Enter to continue'});
        if ~waitForEnter(keys, loadWhileIdle), return; end
    end
end
results = session;
rated = sum(~isnan(session.score));
if rated < n
    showMessage(window, GREY, {sprintf('Session finished: %d / %d done. Thank you!', rated, n)});
    WaitSecs(2);
    fprintf('Session ended after trial %d: %d/%d rated. Rerun with the same subject ID to continue.\n', ...
        sessionEnd, rated, n);
    return;
end
showMessage(window, GREY, {'Finished. Thank you!'});
WaitSecs(2);
fprintf('All %d videos rated. Ratings: %s\n', n, ratingFile);
end

function session = readSession(file)
% Read a session file with fixed column types (subject IDs like "01" stay text).
options = detectImportOptions(file, 'Delimiter', ',');
text = {'subject', 'candidate_id', 'chunk1', 'chunk2', 'chunk3', 'timestamp'};
options = setvartype(options, text, 'string');
options = setvartype(options, setdiff(options.VariableNames, text), 'double');
session = readtable(file, options);
session.timestamp(ismissing(session.timestamp)) = "";
end

function writeSession(session, file)
% Write the whole session (blank cells for unrated trials) to a temporary
% file, then replace FILE, so a crash mid-write never leaves it truncated.
temporary = [file '.partial'];
fid = fopen(temporary, 'w');
assert(fid > 0, 'gmad:SessionFile', 'Cannot write %s.', temporary);
fprintf(fid, '%s\n', strjoin(session.Properties.VariableNames, ','));
for row = 1:height(session)
    cells = cell(1, width(session));
    for col = 1:width(session)
        value = session{row, col};
        if isstring(value)
            cells{col} = char(value);
        elseif isnan(value)
            cells{col} = '';
        else
            cells{col} = num2str(value, 12);
        end
    end
    fprintf(fid, '%s\n', strjoin(cells, ','));
end
fclose(fid);
movefile(temporary, file, 'f');
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
listing = [dir(fullfile(outDir, 'S*_ratings.csv')); dir(fullfile(outDir, 'S*_order.csv'))];
for file = listing'
    token = regexp(file.name, '^S(\d+)', 'tokens', 'once');
    if ~isempty(token), used = max(used, str2double(token{1})); end
end
id = sprintf('S%02d_%s', used + 1, char(datetime('now', 'Format', 'yyyyMMdd')));
end

function [vbl, skipped, quit, flipLog] = playClip(window, resources, slots, chunkSpecs, card, when, cardSeconds, destination, ifi, keys, grey, showInfo, levelText)
% Grey title card, then three consecutive 1.5 s chunks drawn from textures
% decoded in advance by loadClip, so each flip only draws one texture.
% skipped counts frames passed over because a flip came late.
% flipLog rows: [requested_when vbl stimulus_onset flip_end missed chunk frame pts].
quit = false; skipped = 0;
flipLog = nan(ceil(4.5/ifi) + 60, 8); flips = 0;
frames = resources('frames'); pts = resources('pts');
Screen('FillRect', window, grey);
drawLines(window, card, 255);
cardOnset = Screen('Flip', window, when);
frameIndex = ones(1, 3);
onset = []; vbl = [];
while true
    if isempty(onset), elapsed = 0; else, elapsed = vbl + ifi - onset; end
    if elapsed > 4.5 - 0.5*ifi, break; end
    c = min(3, floor(max(0, elapsed) / 1.5) + 1);
    fps = chunkSpecs(c,3);
    f = min(round(1.5*fps), floor(max(0, elapsed - (c-1)*1.5) * fps + 1e-6) + 1);
    skipped = skipped + max(0, f-frameIndex(c)-1);
    frameIndex(c) = max(frameIndex(c), f);
    Screen('FillRect', window, 0);
    % Bilinear GPU scaling; frame repetition supplies native temporal
    % sampling. No optical-flow or blended-frame interpolation.
    Screen('DrawTexture', window, frames{slots(c)}(f), [], destination, 0, 1);
    % Top-left labels: expected level (training), then chunk info (debug).
    labels = {};
    if ~isempty(levelText), labels{end+1} = levelText; end %#ok<AGROW>
    if showInfo, labels{end+1} = sprintf('Chunk %d/3  %dp%d', c, chunkSpecs(c,2), chunkSpecs(c,3)); end %#ok<AGROW>
    y = destination(2) + 16;
    for label = labels
        bounds = Screen('TextBounds', window, label{1});
        Screen('FillRect', window, 0, OffsetRect(GrowRect(bounds, 8, 4), destination(1) + 16, y));
        Screen('DrawText', window, label{1}, destination(1) + 16, y, [255 255 0]);
        y = y + RectHeight(bounds) + 14;
    end
    if isempty(onset)
        requested = cardOnset + cardSeconds - 0.5*ifi;
        [vbl, stimulusOnset, flipEnd, missed] = Screen('Flip', window, requested); onset = vbl;
    else
        requested = vbl + 0.5*ifi;
        [vbl, stimulusOnset, flipEnd, missed] = Screen('Flip', window, requested);
    end
    flips = flips + 1;
    flipLog(flips,:) = [requested vbl stimulusOnset flipEnd missed c f pts{slots(c)}(f)];
    if strcmp(readKey(keys), 'quit'), quit = true; break; end
end
flipLog = flipLog(1:flips,:);
end

function writeFlipLog(outDir, stem, flipLog, chunkSpecs, ifi)
% One CSV per played clip, times relative to the first video flip, plus a
% console summary: unique frames shown and mean on-screen duration per chunk.
if isempty(flipLog), return; end
folder = fullfile(outDir, 'flip_timing');
if ~isfolder(folder), mkdir(folder); end
t0 = flipLog(1,2);
log = array2table([flipLog(:,1:4) - t0, flipLog(:,5:8)], 'VariableNames', ...
    {'requested_s', 'vbl_s', 'stimulus_onset_s', 'flip_end_s', 'missed', 'chunk', 'frame', 'pts_s'});
log.target_fps = chunkSpecs(log.chunk, 3);
log.ifi_s = repmat(ifi, height(log), 1);
writetable(log, fullfile(folder, [stem '.csv']));
intervals = diff(log.vbl_s);
fprintf('  %s: %d flips, interval %.2f +/- %.2f ms (max %.2f), %d late (> 1.5 refresh)\n', stem, ...
    height(log), 1e3*mean(intervals), 1e3*std(intervals), 1e3*max(intervals), sum(intervals > 1.5*ifi));
ends = [log.vbl_s(2:end); log.vbl_s(end) + ifi];   % each flip stays until the next one
for c = unique(log.chunk)'
    rows = find(log.chunk == c);
    frames = numel(unique(log.frame(rows)));
    span = ends(rows(end)) - log.vbl_s(rows(1));
    fprintf('    chunk %d (%d fps target): %d distinct frames in %.3f s -> %.1f fps shown\n', c, ...
        chunkSpecs(c,3), frames, span, frames / span);
end
end

function [score, action, ratingTime] = rateVideo(window, grey, scale, keys, when, footer, idle, progress)
% IDLE runs between key checks (background loading) and returns true when it has nothing to do.
% PROGRESS is the fraction of the session's trials already rated (progress bar).
score = 0; action = '';
KbQueueFlush;
header = {'Rate the impairment of the TEST video compared with the REFERENCE'};
drawScale(window, grey, scale, score, header, footer, progress);
onset = Screen('Flip', window, when);
while isempty(action)
    key = readKey(keys);
    switch key
        case {'1', '2', '3', '4', '5'}
            score = str2double(key);
            drawScale(window, grey, scale, score, header, footer, progress);
            Screen('Flip', window);
        case 'enter'
            if score > 0, action = 'next'; end
        case {'replay', 'quit'}
            action = key;
        otherwise
            if idle(), WaitSecs('YieldSecs', 0.005); end
    end
end
ratingTime = GetSecs - onset;
end

function text = expectedRange(level, scale)
% Training feedback as a range reaching one level below the CVVDP level,
% e.g. level 3 -> '2-3  (Poor to Fair)'; level 1 stays '1  (Bad)'.
name = @(lv) extractBefore(scale{[scale{:,1}] == lv, 2}, ' - ');
if level <= 1
    text = sprintf('%d  (%s)', level, name(level));
else
    text = sprintf('%d-%d  (%s to %s)', level - 1, level, name(level - 1), name(level));
end
end

function drawScale(window, grey, scale, score, header, footer, progress)
% Five DSIS levels as aligned columns: score, label. PROGRESS (0-1, optional)
% adds a session progress bar below the footer.
showProgress = nargin >= 7 && ~isempty(progress);
Screen('FillRect', window, grey);
[width, height] = Screen('WindowSize', window);
rowHeight = round(Screen('TextSize', window) * 1.8);
labelWidth = max(cellfun(@(text) textWidth(window, text), scale(:,2)));
numberWidth = textWidth(window, '5'); gap = rowHeight;
x = (width - (numberWidth + labelWidth + gap)) / 2;
top = (height - (numel(header) + size(scale, 1) + numel(footer) + 2 + showProgress) * rowHeight) / 2;
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
if showProgress
    % Track and fill, then "NN% completed" to the right; fill uses the selection blue.
    barWidth = round(width * 0.35); barHeight = 12;
    y = top + (numel(header) + size(scale, 1) + 2 + numel(footer)) * rowHeight + rowHeight * 0.3;
    left = (width - barWidth) / 2;
    Screen('FillRect', window, 95, [left, y, left + barWidth, y + barHeight]);
    Screen('FillRect', window, [40 90 170], [left, y, left + barWidth * min(1, max(0, progress)), y + barHeight]);
    label = sprintf('%d%% completed', round(100 * progress));
    Screen('DrawText', window, double(label), left + barWidth + 16, ...
        y + barHeight / 2 - Screen('TextSize', window) * 0.6, 220);
end
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
    if isempty(lines{line}), continue; end   % blank spacer line; TextBounds rejects empty text
    Screen('DrawText', window, double(lines{line}), (width - textWidth(window, lines{line})) / 2, ...
        top + (line-1) * rowHeight, color);
end
end

function w = textWidth(window, text)
bounds = Screen('TextBounds', window, double(text));
w = bounds(3) - bounds(1);
end

function ok = waitForEnter(keys, idle)
KbQueueFlush;
while true
    key = readKey(keys);
    if any(strcmp(key, {'enter', 'quit'})), ok = strcmp(key, 'enter'); return; end
    if nargin < 2 || idle(), WaitSecs('YieldSecs', 0.005); end
end
end

function queueTrial(resources, withReference, refPaths, refSpecs, testPaths, testSpecs)
% Queue a trial's chunks for decoding into the next-trial slots: reference
% 7-9 (only when the shot changes), test 10-12. 1080p120 test chunks are the
% reference file and need no decoding.
jobs = resources('jobs');
for c = 1:3
    if withReference
        jobs(end+1) = struct('slot', 6 + c, 'source', refPaths(c), 'spec', refSpecs(c,:)); %#ok<AGROW>
    end
end
for c = 1:3
    if testPaths(c) ~= refPaths(c)
        jobs(end+1) = struct('slot', 9 + c, 'source', testPaths(c), 'spec', testSpecs(c,:)); %#ok<AGROW>
    end
end
resources('jobs') = jobs;
end

function done = stepLoader(window, resources, budget)
% Decode queued chunks into GPU textures for about BUDGET seconds, one frame at
% a time; true once the queue is empty. Each texture is registered as soon as
% it exists, so cleanup works after errors.
start = GetSecs;
jobs = resources('jobs');
while ~isempty(jobs) && GetSecs - start < budget
    job = jobs(1);
    movies = resources('movies');
    if isnan(movies(job.slot))
        [movie, duration, fps, w, h] = Screen('OpenMovie', window, char(job.source), 0, 1);
        movies(job.slot) = movie; resources('movies') = movies;
        assert(w == job.spec(1) && h == job.spec(2) && abs(fps-job.spec(3)) < 1 && abs(duration-1.5) < 0.02, ...
            'gmad:MovieFormat', 'Unexpected movie properties: %s', job.source);
        % Without PlayMovie, frames are only delivered after an explicit seek.
        Screen('SetMovieTimeIndex', movie, 0);
    end
    movie = movies(job.slot);
    frames = resources('frames'); pts = resources('pts');
    frame = numel(frames{job.slot}) + 1;
    try
        [texture, time] = Screen('GetMovieImage', window, movie, 1);
    catch cause
        failure = MException('gmad:DecodeFrame', ...
            'HEVC decoding failed in %s at frame %d. See the preceding Psychtoolbox error.', job.source, frame);
        throw(addCause(failure, cause));
    end
    assert(texture > 0, 'gmad:DecodeFrames', 'Missing frame %d in %s.', frame, job.source);
    frames{job.slot}(frame) = texture; resources('frames') = frames;
    assert(frame == 1 || time > pts{job.slot}(end), 'gmad:DecodeOrder', ...
        'Non-increasing timestamps in %s at frame %d.', job.source, frame);
    pts{job.slot}(frame) = time; resources('pts') = pts;
    if frame == round(1.5 * job.spec(3))
        Screen('CloseMovie', movie);
        movies(job.slot) = nan; resources('movies') = movies;
        % Upload now rather than on first draw, so playback never waits for VRAM transfers.
        Screen('PreloadTextures', window, frames{job.slot});
        jobs(1) = [];
        resources('jobs') = jobs;
    end
end
done = isempty(jobs);
end

function suspendLoader(resources)
% Close a half-decoded chunk and drop its frames; it restarts from frame 1 on
% the next stepLoader call. Queued but unopened chunks are left as they are.
jobs = resources('jobs'); movies = resources('movies');
if isempty(jobs) || isnan(movies(jobs(1).slot)), return; end
closeSlots(resources, jobs(1).slot);
end

function promoteSlots(resources, slots)
% Replace the current chunks in SLOTS with the fully loaded next ones (SLOTS + 6).
closeSlots(resources, slots);
frames = resources('frames'); pts = resources('pts');
frames(slots) = frames(slots + 6); pts(slots) = pts(slots + 6);
frames(slots + 6) = {[]}; pts(slots + 6) = {[]};
resources('frames') = frames; resources('pts') = pts;
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
closeSlots(resources, 1:numel(resources('frames')));
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
movies = resources('movies'); frames = resources('frames'); pts = resources('pts');
if ~isempty(window) && ismember(window, live)
    for movie = movies(slots(isfinite(movies(slots))))
        try Screen('CloseMovie', movie); catch, end
    end
    open = [frames{slots}];
    open = open(open > 0 & ismember(open, live));
    if ~isempty(open), try Screen('Close', open); catch, end, end
end
movies(slots) = nan; frames(slots) = {[]}; pts(slots) = {[]};
resources('movies') = movies; resources('frames') = frames; resources('pts') = pts;
end

function live = liveWindows()
try live = Screen('Windows'); catch, live = []; end
end
