// Harmless demonstration inputs. Each one is blocked by a different gate in
// security.py, so loading one shows the shield doing its job.

export const ATTACKS = [
  {
    id: 'traversal',
    label: 'Path traversal',
    hint: 'Tries to read a file outside the upload folder.',
    code: 'LOAD "../../etc/passwd"\nSAVE "out.png"\n',
  },
  {
    id: 'injection',
    label: 'Code injection',
    hint: 'Smuggles a shell command into the program.',
    code: 'LOAD "input.png"\nos.system("rm -rf /")\nSAVE "out.png"\n',
  },
  {
    id: 'resource',
    label: 'Resource abuse',
    hint: 'Asks for a blur far larger than the server will allow.',
    code: 'LOAD "input.png"\nBLUR 9999\nSAVE "out.png"\n',
  },
  {
    id: 'unknown',
    label: 'Unknown command',
    hint: 'Invokes a command that is not in the whitelist.',
    code: 'LOAD "input.png"\nDELETE_ALL 1\nSAVE "out.png"\n',
  },
]

// What each rejection code means, in plain words.
export const CODE_EXPLAIN = {
  INJECTION_BLOCKED:
    'Stopped before the lexer ran. Nothing in the program was parsed or executed.',
  INVALID_PATH:
    'File names are rejected rather than cleaned up, so "../" never reaches the filesystem.',
  PATH_TRAVERSAL:
    'The resolved path left the sandbox folder, so the request was refused.',
  INVALID_EXTENSION:
    'Only png, jpg, jpeg and webp files can be read or written.',
  INVALID_BLUR: 'The blur radius is above the hard limit, which protects the server from huge workloads.',
  INVALID_RESIZE: 'The requested size is above the hard limit.',
  INVALID_VIGNETTE: 'The vignette strength is outside its allowed range.',
  INVALID_ANGLE: 'Rotations must be a multiple of 90 degrees.',
  TOO_MANY_OPERATIONS: 'The program is longer than the operation limit.',
  UNKNOWN_COMMAND:
    'Only whitelisted commands exist. There is no fallback that guesses what you meant.',
}
