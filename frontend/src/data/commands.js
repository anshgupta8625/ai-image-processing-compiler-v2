// Content for the info (ⓘ) dialog. Prose lives here; numeric ranges are read
// from /api/limits so the guide can never disagree with what the backend
// actually enforces.

const range = (limits, key, fallback) => limits?.[key] ?? fallback

export const COMMANDS = [
  {
    name: 'LOAD',
    syntax: 'LOAD "file"',
    summary: 'Loads the image you uploaded. Must be the first command and appear exactly once.',
    params: () => [
      ['file', 'A quoted plain filename ending in png, jpg, jpeg or webp. No folders and no "..". The image used is always the one you uploaded.'],
    ],
    optimiser: 'Never changed. It sets the pixel count the whole program is costed against.',
    example: 'LOAD "photo.jpg"',
  },
  {
    name: 'RESIZE',
    syntax: 'RESIZE width height',
    summary: 'Scales the image to exactly width × height pixels.',
    params: (l) => {
      const max = range(l, 'max_resize_dim', 4096)
      return [
        ['width', `Whole number of pixels, 1 to ${max}.`],
        ['height', `Whole number of pixels, 1 to ${max}. Width × height is also capped.`],
      ]
    },
    optimiser: 'A RESIZE that shrinks is moved above BLUR, EDGE, GRAYSCALE and VIGNETTE so they run on fewer pixels. One that enlarges is never moved.',
    example: 'RESIZE 400 300',
  },
  {
    name: 'GRAYSCALE',
    syntax: 'GRAYSCALE',
    summary: 'Converts the image to a single brightness channel.',
    params: () => [],
    optimiser: 'A repeated GRAYSCALE is collapsed into one.',
    example: 'GRAYSCALE',
  },
  {
    name: 'BLUR',
    syntax: 'BLUR radius',
    summary: 'Gaussian blur using a (2r+1) × (2r+1) kernel. A larger radius blurs more and costs more.',
    params: (l) => [
      ['radius', `Whole number, 1 to ${range(l, 'max_blur_radius', 25)}.`],
    ],
    optimiser: 'Two blurs in a row are fused into one with radius √(a² + b²).',
    example: 'BLUR 3',
  },
  {
    name: 'ROTATE',
    syntax: 'ROTATE angle',
    summary: 'Rotates the image clockwise by a multiple of 90 degrees, with no resampling.',
    params: () => [
      ['angle', 'A multiple of 90 from -360 to 360. Negative angles are the same turn in the other direction (-90 is 270).'],
    ],
    optimiser: 'Adjacent rotations are merged, and a full turn disappears.',
    example: 'ROTATE 90',
  },
  {
    name: 'EDGE',
    syntax: 'EDGE [low high]',
    summary: 'Canny edge detection. Produces a black and white map of the edges.',
    params: () => [
      ['low', 'Lower hysteresis threshold, 0 or more. Optional; defaults to 100.'],
      ['high', 'Upper threshold, greater than low and at most 500. Optional; defaults to 200. Give both or neither.'],
    ],
    optimiser: 'The most expensive command, so it gains the most when a shrinking RESIZE is moved ahead of it.',
    example: 'EDGE 80 160',
  },
  {
    name: 'VIGNETTE',
    syntax: 'VIGNETTE strength',
    summary: 'Darkens the image smoothly towards the corners and leaves the centre untouched.',
    params: (l) => {
      const [lo, hi] = l?.vignette_range ?? [1, 100]
      return [['strength', `Whole number, ${lo} to ${hi}: the percentage of brightness lost at the corners.`]]
    },
    optimiser: 'The falloff is defined in relative coordinates, so it looks the same at any size. That lets a shrinking RESIZE move above it.',
    example: 'VIGNETTE 60',
  },
  {
    name: 'SAVE',
    syntax: 'SAVE "file"',
    summary: 'Writes the result. Must be the last command.',
    params: () => [
      ['file', 'A quoted plain filename with an allowed extension. The server stores it under a random name and only keeps your extension.'],
    ],
    optimiser: 'Nothing after it can run, so anything following it is removed.',
    example: 'SAVE "result.png"',
  },
]

export const TIPS = [
  'Commands are case-insensitive: blur 3 and BLUR 3 are the same.',
  'Everything from # to the end of a line is a comment.',
  'Order matters. Write the program the way you would think about it; the optimiser reorders it where that is safe.',
  'There are no loops and no variables. That is deliberate: a program that cannot loop cannot run forever.',
]
