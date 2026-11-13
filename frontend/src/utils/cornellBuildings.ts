export interface CornellBuilding {
  key: string;
  name: string;
  lat: number;
  lon: number;
  aliases: string[];
}

// Approximate Ithaca campus building coordinates for walking-time estimation.
// Gracefully ignored whenever locations are TBA, virtual, or unlisted (e.g. during pre-enroll).
const CORNELL_BUILDINGS: CornellBuilding[] = [
  { key: "gates", name: "Gates Hall", lat: 42.4449, lon: -76.4809, aliases: ["gates hall", "bill and melinda gates", "gates"] },
  { key: "bowers", name: "Bowers CIS", lat: 42.4452, lon: -76.4805, aliases: ["bowers", "computing and information science"] },
  { key: "phillips", name: "Phillips Hall", lat: 42.4446, lon: -76.4820, aliases: ["phillips hall", "phillips"] },
  { key: "upson", name: "Upson Hall", lat: 42.4439, lon: -76.4822, aliases: ["upson hall", "upson"] },
  { key: "duffield", name: "Duffield Hall", lat: 42.4442, lon: -76.4827, aliases: ["duffield hall", "duffield"] },
  { key: "kimball", name: "Kimball Hall", lat: 42.4441, lon: -76.4835, aliases: ["kimball hall", "kimball"] },
  { key: "thurston", name: "Thurston Hall", lat: 42.4441, lon: -76.4841, aliases: ["thurston hall", "thurston"] },
  { key: "bard", name: "Bard Hall", lat: 42.4445, lon: -76.4843, aliases: ["bard hall", "bard"] },
  { key: "hollister", name: "Hollister Hall", lat: 42.4443, lon: -76.4847, aliases: ["hollister hall", "hollister"] },
  { key: "olin_hall", name: "Olin Hall", lat: 42.4454, lon: -76.4844, aliases: ["olin hall"] },
  { key: "carpenter", name: "Carpenter Hall", lat: 42.4448, lon: -76.4841, aliases: ["carpenter hall", "carpenter"] },
  { key: "rhodes", name: "Rhodes Hall", lat: 42.4436, lon: -76.4814, aliases: ["rhodes hall", "frank h t rhodes", "rhodes"] },
  { key: "snee", name: "Snee Hall", lat: 42.4445, lon: -76.4852, aliases: ["snee hall", "snee"] },
  { key: "statler", name: "Statler Hall", lat: 42.4458, lon: -76.4821, aliases: ["statler hall", "statler"] },
  { key: "sage", name: "Sage Hall", lat: 42.4459, lon: -76.4831, aliases: ["sage hall", "sage"] },
  { key: "uris", name: "Uris Hall", lat: 42.4472, lon: -76.4822, aliases: ["uris hall", "uris"] },
  { key: "mcgraw", name: "McGraw Hall", lat: 42.4488, lon: -76.4852, aliases: ["mcgraw hall", "mcgraw"] },
  { key: "morrill", name: "Morrill Hall", lat: 42.4482, lon: -76.4852, aliases: ["morrill hall", "morrill"] },
  { key: "white", name: "White Hall", lat: 42.4494, lon: -76.4852, aliases: ["white hall", "white"] },
  { key: "goldwin_smith", name: "Goldwin Smith Hall", lat: 42.4490, lon: -76.4835, aliases: ["goldwin smith", "goldwin smith hall"] },
  { key: "klarman", name: "Klarman Hall", lat: 42.4491, lon: -76.4831, aliases: ["klarman hall", "klarman"] },
  { key: "stimson", name: "Stimson Hall", lat: 42.4477, lon: -76.4828, aliases: ["stimson hall", "stimson"] },
  { key: "lincoln", name: "Lincoln Hall", lat: 42.4501, lon: -76.4836, aliases: ["lincoln hall", "lincoln"] },
  { key: "rockefeller", name: "Rockefeller Hall", lat: 42.4494, lon: -76.4819, aliases: ["rockefeller hall", "rockefeller"] },
  { key: "clark", name: "Clark Hall", lat: 42.4496, lon: -76.4812, aliases: ["clark hall", "clark"] },
  { key: "psb", name: "Physical Sciences Bldg", lat: 42.4499, lon: -76.4817, aliases: ["physical sciences", "physical sci"] },
  { key: "baker", name: "Baker Laboratory", lat: 42.4504, lon: -76.4821, aliases: ["baker laboratory", "baker lab", "olin chemistry", "st olin"] },
  { key: "space_sci", name: "Space Sciences Bldg", lat: 42.4489, lon: -76.4806, aliases: ["space sciences", "space sci"] },
  { key: "malott", name: "Malott Hall", lat: 42.4483, lon: -76.4803, aliases: ["malott hall", "malott"] },
  { key: "bailey", name: "Bailey Hall", lat: 42.4489, lon: -76.4793, aliases: ["bailey hall", "bailey"] },
  { key: "ives", name: "Ives Hall", lat: 42.4475, lon: -76.4798, aliases: ["ives hall", "ives", "ilr conference"] },
  { key: "barton", name: "Barton Hall", lat: 42.4465, lon: -76.4807, aliases: ["barton hall", "barton"] },
  { key: "teagle", name: "Teagle Hall", lat: 42.4459, lon: -76.4794, aliases: ["teagle hall", "teagle"] },
  { key: "sibley", name: "Sibley Hall", lat: 42.4508, lon: -76.4839, aliases: ["sibley hall", "sibley"] },
  { key: "rand", name: "Rand Hall", lat: 42.4508, lon: -76.4829, aliases: ["rand hall", "rand"] },
  { key: "milstein", name: "Milstein Hall", lat: 42.4511, lon: -76.4834, aliases: ["milstein hall", "milstein"] },
  { key: "tjaden", name: "Tjaden Hall", lat: 42.4508, lon: -76.4847, aliases: ["tjaden hall", "tjaden"] },
  { key: "anabel_taylor", name: "Anabel Taylor Hall", lat: 42.4446, lon: -76.4859, aliases: ["anabel taylor"] },
  { key: "myron_taylor", name: "Myron Taylor Hall", lat: 42.4439, lon: -76.4861, aliases: ["myron taylor", "hughes hall"] },
  { key: "schwartz", name: "Schwartz Center", lat: 42.4426, lon: -76.4855, aliases: ["schwartz center", "schwartz"] },
  { key: "warren", name: "Warren Hall", lat: 42.4494, lon: -76.4773, aliases: ["warren hall", "warren"] },
  { key: "mann", name: "Mann Library", lat: 42.4488, lon: -76.4763, aliases: ["mann library", "mann"] },
  { key: "kennedy", name: "Kennedy Hall", lat: 42.4484, lon: -76.4777, aliases: ["kennedy hall", "kennedy"] },
  { key: "roberts", name: "Roberts Hall", lat: 42.4484, lon: -76.4783, aliases: ["roberts hall", "roberts"] },
  { key: "caldwell", name: "Caldwell Hall", lat: 42.4485, lon: -76.4769, aliases: ["caldwell hall", "caldwell"] },
  { key: "comstock", name: "Comstock Hall", lat: 42.4479, lon: -76.4772, aliases: ["comstock hall", "comstock"] },
  { key: "plant_sci", name: "Plant Science Bldg", lat: 42.4482, lon: -76.4754, aliases: ["plant science", "plant sci"] },
  { key: "emerson", name: "Emerson Hall", lat: 42.4476, lon: -76.4748, aliases: ["emerson hall", "emerson"] },
  { key: "bradfield", name: "Bradfield Hall", lat: 42.4472, lon: -76.4742, aliases: ["bradfield hall", "bradfield"] },
  { key: "stocking", name: "Stocking Hall", lat: 42.4475, lon: -76.4727, aliases: ["stocking hall", "stocking"] },
  { key: "morrison", name: "Morrison Hall", lat: 42.4480, lon: -76.4706, aliases: ["morrison hall", "morrison"] },
  { key: "riley_robb", name: "Riley-Robb Hall", lat: 42.4465, lon: -76.4718, aliases: ["riley-robb", "riley robb"] },
  { key: "fernow", name: "Fernow Hall", lat: 42.4493, lon: -76.4750, aliases: ["fernow hall", "fernow"] },
  { key: "rice", name: "Rice Hall", lat: 42.4493, lon: -76.4740, aliases: ["rice hall", "rice"] },
  { key: "mvr", name: "Martha Van Rensselaer", lat: 42.4501, lon: -76.4785, aliases: ["martha van rensselaer", "mvr", "human ecology"] },
  { key: "savage", name: "Savage Hall", lat: 42.4505, lon: -76.4805, aliases: ["savage hall", "savage", "kinzelberg"] },
  { key: "corson_mudd", name: "Corson-Mudd Hall", lat: 42.4469, lon: -76.4779, aliases: ["corson", "mudd hall"] },
  { key: "biotech", name: "Biotechnology Bldg", lat: 42.4461, lon: -76.4779, aliases: ["biotechnology", "biotech"] },
  { key: "weill", name: "Weill Hall", lat: 42.4462, lon: -76.4767, aliases: ["weill hall", "weill"] },
  { key: "vet", name: "Schurman Hall (Vet)", lat: 42.4471, lon: -76.4658, aliases: ["schurman", "vet research", "vet medical", "tower road"] },
  { key: "tang", name: "Tang Hall (NYC/Other)", lat: 42.4450, lon: -76.4825, aliases: ["tang hall"] },
];

const IGNORE_TOKENS = [
  "tba",
  "to be arranged",
  "online",
  "virtual",
  "remote",
  "distance",
  "zoom",
  "nyc",
  "cornell tech",
  "washington",
  "off campus",
  "off-campus",
];

export function parseCornellBuilding(
  facilityDescr?: string | null,
  buildingDescr?: string | null
): CornellBuilding | null {
  const combined = `${facilityDescr || ""} ${buildingDescr || ""}`.trim().toLowerCase();
  if (!combined) return null;
  for (const ignore of IGNORE_TOKENS) {
    if (combined.includes(ignore)) return null;
  }

  for (const bldg of CORNELL_BUILDINGS) {
    for (const alias of bldg.aliases) {
      if (combined.includes(alias)) {
        return bldg;
      }
    }
  }
  return null;
}

function haversineMeters(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const r = 6371000;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * r * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

export function estimateWalkMinutes(a: CornellBuilding, b: CornellBuilding): number {
  if (a.key === b.key) return 0;
  const straightMeters = haversineMeters(a.lat, a.lon, b.lat, b.lon);
  // Campus sidewalk + hill detour factor (~1.32x) at ~80 m/min brisk walk
  const walkMin = Math.round((straightMeters * 1.32) / 80);
  return Math.max(1, walkMin);
}

export interface WalkTransitionWarning {
  day: string;
  fromCourse: string;
  toCourse: string;
  fromBuilding: string;
  toBuilding: string;
  gapMin: number;
  walkMin: number;
  isTight: boolean;
  startMin: number;
}

export interface DayTransitionSlot {
  startMin: number;
  endMin: number;
  courseLabel: string;
  facilityDescr?: string | null;
  buildingDescr?: string | null;
}

export function analyzeDayTransitions(
  day: string,
  slots: DayTransitionSlot[]
): WalkTransitionWarning[] {
  if (slots.length < 2) return [];
  const sorted = [...slots].sort((a, b) => a.startMin - b.startMin);
  const warnings: WalkTransitionWarning[] = [];

  for (let i = 0; i < sorted.length - 1; i += 1) {
    const prev = sorted[i];
    const next = sorted[i + 1];
    const gapMin = next.startMin - prev.endMin;
    if (gapMin <= 0 || gapMin > 25) continue;

    const b1 = parseCornellBuilding(prev.facilityDescr, prev.buildingDescr);
    const b2 = parseCornellBuilding(next.facilityDescr, next.buildingDescr);
    // Robust to pre-enroll / TBA / virtual: skip walk estimation if either building is unknown
    if (!b1 || !b2 || b1.key === b2.key) continue;

    const walkMin = estimateWalkMinutes(b1, b2);
    const isTight = walkMin >= gapMin - 3 || walkMin >= 11;
    if (isTight) {
      warnings.push({
        day,
        fromCourse: prev.courseLabel,
        toCourse: next.courseLabel,
        fromBuilding: b1.name,
        toBuilding: b2.name,
        gapMin,
        walkMin,
        isTight,
        startMin: next.startMin,
      });
    }
  }
  return warnings;
}
