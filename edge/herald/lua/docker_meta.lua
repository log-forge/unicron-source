local ok, cjson = pcall(require, "cjson.safe")
if not ok then ok, cjson = pcall(require, "cjson") end
local HAS_CJSON = ok

local DOCKER_DIR = "/var/lib/docker/containers/"
local CACHE_TTL_SEC = tonumber(os.getenv("DOCKER_META_CACHE_TTL") or "") or 300
if CACHE_TTL_SEC < 0 then CACHE_TTL_SEC = 0 end

local cache = {}

-- ===== helpers =====
local function now()
  local ok, t = pcall(os.time)
  if ok and type(t) == "number" then return t end
  return nil
end

local function cache_fresh(entry)
  if not entry then return false end
  if CACHE_TTL_SEC == 0 then return true end
  if not entry.ts then return true end
  local t = now(); if not t then return true end
  return (t - entry.ts) <= CACHE_TTL_SEC
end

local function read_file(p)
  local f = io.open(p, "r"); if not f then return nil end
  local s = f:read("*a"); f:close(); return s
end

local function guess_cid(rec, tag)
  if rec["container.id"] then return rec["container.id"] end
  if rec.path then
    local cid = rec.path:match("/containers/([0-9a-f]+)")
    if cid then return cid end
  end
  if tag then
    local cid = tag:match("([0-9a-f]+)")
    if cid and #cid >= 12 and #cid <= 64 then return cid end
    cid = tag:match("%.([0-9a-f]+)$")
    if cid and #cid >= 12 and #cid <= 64 then return cid end
  end
  return nil
end

local function split_image(ref)
  if not ref or ref == "" then return nil, nil end
  if ref:find("@",1,true) then
    local name = ref:match("^(.-)@")
    return (name ~= "" and name or nil), nil
  end
  local name, tag = ref:match("^(.*):([^/:]+)$")
  if name and tag then return name, tag end
  return ref, "latest"
end

-- ===== parse metadata from JSON =====
local function parse_meta(js)
  local out = {}

  -- container.name
  local cname = js.Name or (js.Config and js.Config.Hostname) or ""
  if cname ~= "" and cname:sub(1,1) == "/" then cname = cname:sub(2) end
  if cname ~= "" then out["container.name"] = cname end

  -- image fields
  local image_ref = (js.Config and js.Config.Image) or js.Image
  if image_ref and image_ref ~= "" then
    local name, tag = split_image(image_ref)
    if name then out["image.name"] = name end
    if tag then out["image.tag"] = tag end
  end

  return out
end

local function load_meta(cid)
  local e = cache[cid]
  if e and cache_fresh(e) then return e.data end

  local raw = read_file(DOCKER_DIR .. cid .. "/config.v2.json")
  if not raw or not HAS_CJSON then
    cache[cid] = false
    return nil
  end

  local okd, js = pcall(cjson.decode, raw)
  if not okd or type(js) ~= "table" then
    cache[cid] = false
    return nil
  end

  local data = parse_meta(js)
  cache[cid] = { data = data, ts = now() }
  return data
end

-- ===== main =====
function enrich(tag, ts, rec)
  local cid = guess_cid(rec, tag)
  if not cid then return 1, ts, rec end

  rec["container.id"] = cid
  local meta = load_meta(cid)

  -- Build resource attributes using underscored names for downstream systems
  -- (Prometheus/VictoriaMetrics label names cannot contain dots).
  local attrs = { ["container_id"] = cid }

  if meta then
    for k,v in pairs(meta) do
      -- keep the original dotted key on the record for log consumers
      rec[k] = v
      -- convert dotted key to underscored key for resource attributes
      local ukey = k:gsub("%.", "_")
      attrs[ukey] = v
    end
  end

  -- Add static herald/service attributes from environment (defensive defaults)
  local herald_id = os.getenv("HERALD_ID") or ""
  local herald_name = os.getenv("HERALD_NAME") or ""
  local environment = os.getenv("ENVIRONMENT") or ""

  if herald_id ~= "" then
    -- keep dotted keys on the record, set underscored keys for resource attrs
    rec["herald.id"] = herald_id
    attrs["herald_id"] = herald_id
    -- service.instance.id is commonly used by telemetry SDKs
    rec["service.instance.id"] = herald_id
    attrs["service_instance_id"] = herald_id
  end

  if herald_name ~= "" then
    rec["herald.name"] = herald_name
    attrs["herald_name"] = herald_name
    rec["service.name"] = herald_name
    attrs["service_name"] = herald_name
  end

  if environment ~= "" then
    rec["herald.env"] = environment
    attrs["herald_env"] = environment
  end

  -- Always set service.namespace to the static value (underscored for resource attrs)
  rec["service.namespace"] = "unicron.herald"
  attrs["service_namespace"] = "unicron.herald"

  -- Wrap into resource.attributes
  rec["resource"] = { attributes = attrs }

  return 1, ts, rec
end