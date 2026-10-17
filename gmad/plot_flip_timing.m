function plot_flip_timing(csvFile)
% PLOT_FLIP_TIMING Plot a per-flip log written by run_dsis_gmad_480p1080p (LOG_FLIP_TIMING = true).
%   plot_flip_timing('.../flip_timing/S01_trial001_play1_reference.csv')
%   plot_flip_timing   % newest log under results/dsis_version_a_*/flip_timing
% Panels:
%   1. Interval between consecutive flips. Should sit on one refresh (~8.34 ms at 120 Hz).
%   2. Decoded frame shown at each flip vs the ideal native-rate frame.
%   3. How long each distinct video frame stayed on screen. At 120 fps every
%      frame should last one refresh; 2+ refreshes means a held (repeated) frame.
if nargin < 1 || isempty(csvFile)
    resultsRoot = fullfile(fileparts(fileparts(mfilename('fullpath'))), 'results');
    listing = dir(fullfile(resultsRoot, 'dsis_version_a_*', 'flip_timing', '*.csv'));
    assert(~isempty(listing), 'gmad:NoFlipLogs', 'No flip logs under %s.', resultsRoot);
    [~, newest] = max([listing.datenum]);
    csvFile = fullfile(listing(newest).folder, listing(newest).name);
end
log = readtable(csvFile);
ifi = log.ifi_s(1);
[~, name] = fileparts(csvFile);
colors = lines(3);

figure('Name', name, 'Color', 'w', 'Position', [100 100 1100 850]);
tiledlayout(3, 1, 'TileSpacing', 'compact');
sgtitle(strrep(name, '_', '\_'));

% 1. Flip-to-flip interval.
nexttile; hold on;
intervals = 1e3 * diff(log.vbl_s);
for c = unique(log.chunk)'
    rows = find(log.chunk(2:end) == c);
    plot(log.vbl_s(rows+1), intervals(rows), '.', 'Color', colors(c,:), ...
        'DisplayName', sprintf('chunk %d (%d fps)', c, log.target_fps(find(log.chunk == c, 1))));
end
late = find(intervals > 1.5e3*ifi);
plot(log.vbl_s(late+1), intervals(late), 'ro', 'DisplayName', sprintf('late (%d)', numel(late)));
yline(1e3*ifi, 'k--', sprintf('1 refresh = %.2f ms', 1e3*ifi), 'HandleVisibility', 'off');
ylabel('flip interval (ms)'); xlabel('time since first video flip (s)');
ylim([0 max([3e3*ifi; intervals])]); legend('Location', 'northeastoutside'); grid on;

% 2. Displayed frame vs ideal frame within each chunk.
nexttile; hold on;
for c = unique(log.chunk)'
    rows = log.chunk == c;
    t = log.vbl_s(rows); fps = log.target_fps(find(rows, 1));
    ideal = min(round(1.5*fps), floor((t - t(1)) * fps + 1e-6) + 1);
    stairs(t, log.frame(rows), 'Color', colors(c,:), 'LineWidth', 1.2, 'DisplayName', sprintf('chunk %d shown', c));
    plot(t, ideal, ':', 'Color', colors(c,:), 'HandleVisibility', 'off');
end
ylabel('frame index in chunk'); xlabel('time since first video flip (s)');
title('solid = frame shown, dotted = ideal at native fps', 'FontWeight', 'normal');
legend('Location', 'northeastoutside'); grid on;

% 3. On-screen duration of each distinct frame, in refreshes.
nexttile; hold on;
ends = [log.vbl_s(2:end); log.vbl_s(end) + ifi];
starts = [true; diff(log.frame) ~= 0 | diff(log.chunk) ~= 0];
first = find(starts); last = [first(2:end) - 1; height(log)];
duration = (ends(last) - log.vbl_s(first)) / ifi;
for c = unique(log.chunk)'
    rows = log.chunk(first) == c;
    fps = log.target_fps(find(log.chunk == c, 1));
    plot(log.vbl_s(first(rows)), duration(rows), '.', 'Color', colors(c,:), 'MarkerSize', 10, ...
        'DisplayName', sprintf('chunk %d: expect %.0f refresh', c, round(1/(fps*ifi))));
end
ylabel('frame on screen (refreshes)'); xlabel('time since first video flip (s)');
ylim([0 max(5, ceil(max(duration)) + 1)]); legend('Location', 'northeastoutside'); grid on;

% Console summary per chunk.
fprintf('%s\n', csvFile);
for c = unique(log.chunk)'
    rows = log.chunk(first) == c;
    fps = log.target_fps(find(log.chunk == c, 1));
    span = sum(duration(rows)) * ifi;
    fprintf('  chunk %d: target %3d fps, shown %6.1f fps, %d frames, %d held longer than expected\n', ...
        c, fps, sum(rows) / span, sum(rows), sum(duration(rows) > round(1/(fps*ifi)) + 0.5));
end
end
