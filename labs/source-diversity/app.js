"use strict";

const ui = {
  form: document.querySelector("#filters"),
  date: document.querySelector("#date-filter"),
  section: document.querySelector("#section-filter"),
  sourceType: document.querySelector("#source-type-filter"),
  export: document.querySelector("#export-csv"),
  status: document.querySelector("#result-status"),
  error: document.querySelector("#load-error"),
  snapshotRange: document.querySelector("#snapshot-range"),
  snapshotGenerated: document.querySelector("#snapshot-generated"),
  snapshotVersion: document.querySelector("#snapshot-version"),
  metricEvents: document.querySelector("#metric-events"),
  metricLinks: document.querySelector("#metric-links"),
  metricPublishers: document.querySelector("#metric-publishers"),
  metricSingle: document.querySelector("#metric-single"),
  regionChart: document.querySelector("#region-chart"),
  publisherChart: document.querySelector("#publisher-chart"),
  typeChart: document.querySelector("#type-chart"),
  singleSourceList: document.querySelector("#single-source-list"),
  auditRows: document.querySelector("#audit-rows"),
};

const numberFormatter = new Intl.NumberFormat("zh-CN");
let dataset = null;

function formatNumber(value) {
  return numberFormatter.format(Number(value) || 0);
}

function formatDate(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return value || "—";
  }
  const [year, month, day] = value.split("-");
  return `${year}.${month}.${day}`;
}

function formatDateTime(value) {
  if (!value) return "未记录";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(parsed);
}

function sectionLabel(section) {
  return section === "ai" ? "AI 前沿" : "世界事件";
}

function assertDataset(value) {
  if (!value || typeof value !== "object") {
    throw new Error("data.json 顶层必须是对象");
  }
  if (!Array.isArray(value.events) || !Array.isArray(value.dates)) {
    throw new Error("data.json 缺少 events 或 dates 数组");
  }
  for (const [index, event] of value.events.entries()) {
    if (!event || typeof event !== "object" || !Array.isArray(event.sources)) {
      throw new Error(`data.json 中 events[${index}] 结构无效`);
    }
  }
  return value;
}

function addOption(select, value, label) {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = label;
  select.append(option);
}

function populateFilters(data) {
  const dates = [...new Set(data.dates.map((row) => row.date).filter(Boolean))];
  dates.sort().reverse();
  for (const date of dates) addOption(ui.date, date, formatDate(date));

  const sourceTypes = [
    ...new Set(
      data.events.flatMap((event) =>
        event.sources.map((source) => source.source_type).filter(Boolean),
      ),
    ),
  ];
  sourceTypes.sort((left, right) => left.localeCompare(right, "zh-CN"));
  for (const sourceType of sourceTypes) {
    addOption(ui.sourceType, sourceType, sourceType);
  }
}

function selectedFilters() {
  return {
    date: ui.date.value,
    section: ui.section.value,
    sourceType: ui.sourceType.value,
  };
}

function visibleSources(event, filters) {
  if (filters.sourceType === "all") return event.sources;
  return event.sources.filter(
    (source) => source.source_type === filters.sourceType,
  );
}

function filteredEvents(filters) {
  return dataset.events.filter((event) => {
    if (filters.date !== "all" && event.date !== filters.date) return false;
    if (filters.section !== "all" && event.section !== filters.section) return false;
    if (
      filters.sourceType !== "all" &&
      !event.sources.some((source) => source.source_type === filters.sourceType)
    ) {
      return false;
    }
    return true;
  });
}

function rankedCounts(values) {
  const counts = new Map();
  for (const value of values) {
    const name = String(value || "未标注");
    counts.set(name, (counts.get(name) || 0) + 1);
  }
  return [...counts.entries()]
    .map(([name, count]) => ({ name, count }))
    .sort(
      (left, right) =>
        right.count - left.count || left.name.localeCompare(right.name, "zh-CN"),
    );
}

function emptyMessage(container, message) {
  container.replaceChildren();
  const item = document.createElement("li");
  item.className = "empty-state";
  item.textContent = message;
  container.append(item);
}

function renderBarChart(container, rows, limit = 12) {
  container.replaceChildren();
  if (!rows.length) {
    emptyMessage(container, "当前筛选下没有可绘制的数据。");
    return;
  }

  const maximum = Math.max(...rows.map((row) => row.count), 1);
  const visible = rows.slice(0, limit);
  for (const row of visible) {
    const item = document.createElement("li");
    item.className = "bar-row";

    const label = document.createElement("div");
    label.className = "bar-row__label";

    const name = document.createElement("span");
    name.className = "bar-row__name";
    name.textContent = row.name;
    name.title = row.name;

    const value = document.createElement("span");
    value.className = "bar-row__value";
    value.textContent = formatNumber(row.count);

    const track = document.createElement("div");
    track.className = "bar-row__track";
    track.setAttribute("aria-hidden", "true");
    const fill = document.createElement("div");
    fill.className = "bar-row__fill";
    fill.style.setProperty("--bar-size", `${(row.count / maximum) * 100}%`);
    track.append(fill);

    label.append(name, value);
    item.append(label, track);
    container.append(item);
  }

  if (rows.length > limit) {
    const remainder = document.createElement("li");
    remainder.className = "empty-state";
    remainder.textContent = `图表显示前 ${limit} 项；另有 ${rows.length - limit} 项可在明细表与 CSV 中审计。`;
    container.append(remainder);
  }
}

function renderMetrics(events, filters) {
  const sources = events.flatMap((event) => visibleSources(event, filters));
  const publishers = new Set(sources.map((source) => source.publisher));
  const singleSourceEvents = events.filter((event) => event.single_source);

  ui.metricEvents.textContent = formatNumber(events.length);
  ui.metricLinks.textContent = formatNumber(sources.length);
  ui.metricPublishers.textContent = formatNumber(publishers.size);
  ui.metricSingle.textContent = formatNumber(singleSourceEvents.length);
}

function createSourceAnchor(source) {
  const link = document.createElement("a");
  link.href = source.url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = source.title || source.url;
  return link;
}

function renderWatchlist(events) {
  const singleSourceEvents = events.filter((event) => event.single_source);
  ui.singleSourceList.replaceChildren();
  if (!singleSourceEvents.length) {
    emptyMessage(ui.singleSourceList, "当前筛选内没有单一来源事件。");
    return;
  }

  for (const event of singleSourceEvents) {
    const item = document.createElement("li");
    item.className = "watch-item";

    const meta = document.createElement("p");
    meta.className = "watch-item__meta";
    meta.textContent = `${formatDate(event.date)} · ${sectionLabel(event.section)} · ${(event.regions || []).join(" / ")}`;

    const title = document.createElement("p");
    title.className = "watch-item__title";
    title.textContent = event.title;

    const sourceLine = document.createElement("p");
    sourceLine.className = "watch-item__source";
    const source = event.sources[0];
    if (source) {
      sourceLine.append(`${source.publisher} · ${source.source_type} · `);
      sourceLine.append(createSourceAnchor(source));
    } else {
      sourceLine.textContent = "未记录可访问来源";
    }

    item.append(meta, title, sourceLine);
    ui.singleSourceList.append(item);
  }
}

function createCell() {
  return document.createElement("td");
}

function renderAuditTable(events, filters) {
  ui.auditRows.replaceChildren();
  if (!events.length) {
    const row = document.createElement("tr");
    const cell = createCell();
    cell.colSpan = 5;
    cell.className = "empty-state";
    cell.textContent = "当前筛选下没有事件。";
    row.append(cell);
    ui.auditRows.append(row);
    return;
  }

  for (const event of events) {
    const row = document.createElement("tr");

    const dateCell = createCell();
    const meta = document.createElement("div");
    meta.className = "table-meta";
    const date = document.createElement("time");
    date.dateTime = event.date;
    date.textContent = formatDate(event.date);
    const section = document.createElement("span");
    section.className = `section-tag${event.section === "ai" ? " section-tag--ai" : ""}`;
    section.textContent = sectionLabel(event.section);
    meta.append(date, section);
    dateCell.append(meta);

    const eventCell = createCell();
    const eventTitle = document.createElement("span");
    eventTitle.className = "event-title";
    eventTitle.textContent = event.title;
    const eventId = document.createElement("span");
    eventId.className = "event-id";
    eventId.textContent = `${event.category} / ${event.id}`;
    eventCell.append(eventTitle, eventId);

    const regionsCell = createCell();
    const regions = document.createElement("ul");
    regions.className = "tag-list";
    for (const region of event.regions || []) {
      const item = document.createElement("li");
      item.className = "region-tag";
      item.textContent = region;
      regions.append(item);
    }
    regionsCell.append(regions);

    const sourcesCell = createCell();
    const sourceList = document.createElement("ul");
    sourceList.className = "source-list";
    const sources = visibleSources(event, filters);
    if (!sources.length) {
      const item = document.createElement("li");
      item.textContent = "未记录可访问来源";
      sourceList.append(item);
    } else {
      for (const source of sources) {
        const item = document.createElement("li");
        item.className = "source-link";
        const identity = document.createElement("span");
        const publisher = document.createElement("span");
        publisher.className = "source-link__publisher";
        publisher.textContent = source.publisher;
        const type = document.createElement("span");
        type.className = "source-link__type";
        type.textContent = ` / ${source.source_type}`;
        identity.append(publisher, type);
        item.append(identity, createSourceAnchor(source));
        sourceList.append(item);
      }
    }
    sourcesCell.append(sourceList);

    const confidenceCell = createCell();
    const confidence = document.createElement("span");
    confidence.className = "confidence";
    confidence.textContent = event.confidence || "unspecified";
    confidenceCell.append(confidence);

    row.append(dateCell, eventCell, regionsCell, sourcesCell, confidenceCell);
    ui.auditRows.append(row);
  }
}

function renderCharts(events, filters) {
  const regions = rankedCounts(
    events.flatMap((event) => event.regions || ["Unspecified"]),
  );
  const sources = events.flatMap((event) => visibleSources(event, filters));
  const publishers = rankedCounts(sources.map((source) => source.publisher));
  const sourceTypes = rankedCounts(sources.map((source) => source.source_type));

  renderBarChart(ui.regionChart, regions, 16);
  renderBarChart(ui.publisherChart, publishers, 12);
  renderBarChart(ui.typeChart, sourceTypes, 12);
}

function renderStatus(events, filters) {
  const sourceLinks = events.reduce(
    (sum, event) => sum + visibleSources(event, filters).length,
    0,
  );
  const scope = [
    ui.date.selectedOptions[0]?.textContent,
    ui.section.selectedOptions[0]?.textContent,
    ui.sourceType.selectedOptions[0]?.textContent,
  ]
    .filter(Boolean)
    .join(" / ");
  ui.status.textContent = `${scope}：${formatNumber(events.length)} 个事件，${formatNumber(sourceLinks)} 条来源链接。`;
}

function render() {
  if (!dataset) return;
  const filters = selectedFilters();
  const events = filteredEvents(filters);
  renderMetrics(events, filters);
  renderCharts(events, filters);
  renderWatchlist(events);
  renderAuditTable(events, filters);
  renderStatus(events, filters);
}

function csvCell(value) {
  let text = value == null ? "" : String(value);
  if (/^[=+\-@]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

function buildCsv(events, filters) {
  const header = [
    "date",
    "section",
    "event_id",
    "category",
    "event_title",
    "regions",
    "confidence",
    "publisher",
    "source_type",
    "source_title",
    "published_at",
    "url",
    "original_source_count",
  ];
  const rows = [header];

  for (const event of events) {
    const sources = visibleSources(event, filters);
    const auditableSources = sources.length ? sources : [{}];
    for (const source of auditableSources) {
      rows.push([
        event.date,
        event.section,
        event.id,
        event.category,
        event.title,
        (event.regions || []).join(" | "),
        event.confidence,
        source.publisher,
        source.source_type,
        source.title,
        source.published_at,
        source.url,
        event.source_count,
      ]);
    }
  }
  return rows.map((row) => row.map(csvCell).join(",")).join("\r\n");
}

function exportCsv() {
  if (!dataset) return;
  const filters = selectedFilters();
  const events = filteredEvents(filters);
  const csv = `\ufeff${buildCsv(events, filters)}`;
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  const datePart = filters.date === "all" ? "all-dates" : filters.date;
  link.href = url;
  link.download = `world-pulse-source-diversity-${datePart}.csv`;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function setSnapshotDetails(data) {
  const start = data.date_range?.start;
  const end = data.date_range?.end;
  ui.snapshotRange.textContent =
    start && end ? `${formatDate(start)} — ${formatDate(end)}` : "暂无日报";
  ui.snapshotGenerated.textContent = formatDateTime(
    data.latest_digest_generated_at,
  );
  ui.snapshotVersion.textContent = `schema v${data.schema_version ?? "?"}`;
}

async function load() {
  try {
    const response = await fetch("data.json", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`读取 data.json 失败（HTTP ${response.status}）`);
    }
    dataset = assertDataset(await response.json());
    populateFilters(dataset);
    setSnapshotDetails(dataset);
    ui.export.disabled = false;
    render();
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    ui.error.hidden = false;
    ui.error.textContent = `${detail}。请先运行构建器，并通过本地 HTTP 服务打开本页（不要直接使用 file://）。`;
    ui.status.textContent = "审计数据尚未载入。";
  }
}

ui.form.addEventListener("change", render);
ui.form.addEventListener("reset", () => window.setTimeout(render, 0));
ui.export.addEventListener("click", exportCsv);

load();
