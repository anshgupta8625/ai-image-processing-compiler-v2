# AI Image Processing Compiler

A domain-specific language (DSL) compiler for image processing that lets users write simple commands to transform images through a web-based interface.

The project combines compiler design, image processing, optimization, and full-stack web development in one application.

## Overview

Instead of manually applying image filters through separate tools, users can write a small program using the Image Processing DSL. The compiler parses the program, validates its commands, processes the requested transformations, and produces an output image.

### Key Features

- **Custom DSL:** A simple command-based language for image manipulation.
- **Compiler pipeline:** Lexical analysis, parsing, semantic validation, intermediate representation, and execution.
- **16 image-processing commands:** Supports basic and advanced transformations.
- **Optimization:** Compiler optimization passes for supported operations.
- **Web interface:** React and Vite frontend for writing and running DSL programs.
- **Python API:** FastAPI backend for compilation and image-processing requests.
- **Validation and security:** Input validation, command restrictions, and resource limits.
- **Testing:** Automated tests for compiler functionality, parsing, API behavior, and new commands.

## Technology Stack

| Component | Technology |
|---|---|
| Frontend | React, Vite, JavaScript |
| Backend | Python, FastAPI |
| Compiler | Custom DSL lexer, parser, semantic analyzer, and intermediate representation |
| Image processing | OpenCV, NumPy |
| API server | Uvicorn |
| Testing | pytest |
| Version control | Git and GitHub |

## Supported DSL Commands

The language supports 16 commands.

| Command | Purpose | Example |
|---|---|---|
| `LOAD` | Load an input image | `LOAD "input.jpg"` |
| `SAVE` | Save the processed image | `SAVE "output.jpg"` |
| `RESIZE` | Change image dimensions | `RESIZE 800 600` |
| `GRAYSCALE` | Convert to grayscale | `GRAYSCALE` |
| `BLUR` | Apply blur | `BLUR 3` |
| `ROTATE` | Rotate an image | `ROTATE 90` |
| `EDGE` | Detect edges | `EDGE 100 200` |
| `VIGNETTE` | Apply a vignette effect | `VIGNETTE 50` |
| `BRIGHTNESS` | Adjust brightness | `BRIGHTNESS 20` |
| `CONTRAST` | Adjust contrast | `CONTRAST 1.2` |
| `SATURATION` | Adjust color saturation | `SATURATION 1.5` |
| `FLIP` | Flip an image horizontally or vertically | `FLIP HORIZONTAL` |
| `CROP` | Crop a rectangular image region | `CROP 0 0 300 300` |
| `SHARPEN` | Enhance image details | `SHARPEN` |
| `THRESHOLD` | Apply intensity thresholding | `THRESHOLD 128` |
| `MEDIAN_BLUR` | Apply median filtering | `MEDIAN_BLUR 3` |

*Examples show the intended DSL syntax. Valid argument ranges and behavior are determined by the implementation.*

## Example Program

```text
LOAD "input.jpg"
BRIGHTNESS 20
CONTRAST 1.2
SATURATION 1.5
FLIP HORIZONTAL
SHARPEN
SAVE "output.jpg"
```

This program loads an image, applies several transformations, and saves the result.

Another example using the original commands:

```text
LOAD "input.jpg"
GRAYSCALE
BLUR 3
ROTATE 90
SAVE "output.jpg"
```

## Architecture

The application follows a compiler-based processing pipeline.

```text
User writes DSL program
          |
          v
     React Frontend
          |
          v
      FastAPI API
          |
          v
      Lexical Analysis
          |
          v
         Parser
          |
          v
    Semantic Analysis
          |
          v
 Intermediate Representation
          |
          v
      Optimization
          |
          v
    Image Execution
          |
          v
     Output Image
```

The lexer identifies tokens, the parser builds a structured program, semantic analysis validates commands and arguments, and the subsequent compiler stages prepare and execute the image-processing operations.

## Project Structure

```text
ai-image-processing-compiler-v2/
├── backend/
│   ├── app.py
│   ├── security.py
│   ├── config.py
│   ├── compiler/
│   │   ├── lexer.py
│   │   ├── parser.py
│   │   ├── semantic.py
│   │   ├── ast_nodes.py
│   │   ├── ir.py
│   │   ├── optimizer.py
│   │   ├── executor.py
│   │   ├── pipeline.py
│   │   ├── trace.py
│   │   └── errors.py
│   └── tests/
├── frontend/
│   └── src/
├── docs/
├── examples/
├── requirements.txt
└── README.md
```

## Getting Started

### Prerequisites

Install the following:

- Python 3.10 or a compatible version supported by the project's dependencies
- Node.js and npm
- Git

### 1. Clone the repository

```bash
git clone https://github.com/anshgupta8625/ai-image-processing-compiler-v2.git
cd ai-image-processing-compiler-v2
```

### 2. Set up the backend

On Windows PowerShell:

```powershell
cd backend

python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

If `requirements.txt` is located in the repository root rather than `backend`, run the installation command from the root using:

```powershell
pip install -r .\requirements.txt
```

Start the API from the `backend` directory:

```powershell
python -m uvicorn app:app --reload
```

The local API should be available at:

- API: http://127.0.0.1:8000
- Interactive API documentation: http://127.0.0.1:8000/docs

### 3. Set up the frontend

Open a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open the local URL printed by Vite, usually:

http://localhost:5173/

### 4. Run the application

1. Open the frontend in your browser.
2. Upload or select an input image using the application's interface.
3. Enter a DSL program in the editor.
4. Execute the program.
5. Inspect the processing result and any compiler diagnostics.

Use the interface's expected image-upload and output workflow when choosing filenames in your DSL program.

## Running Tests

From the `backend` directory, activate the virtual environment and run:

```powershell
python -m pytest -v
```

To run the tests specifically covering the new commands:

```powershell
python -m pytest tests/test_new_commands.py -v
```

## Deployment

The frontend and backend can be deployed independently.

- **Frontend:** Vercel
- **Backend:** Render

The deployed frontend must use the public backend API URL instead of `localhost`. Configure the production API endpoint and CORS settings appropriately before deployment.

**Live demo:** Add the Vercel URL after deployment.

**Backend API:** Add the Render URL after deployment.

## Security Considerations

- Validate DSL commands and their arguments before execution.
- Restrict file access to permitted input and output locations.
- Apply operation-count and image-processing resource limits.
- Keep credentials and environment-specific secrets out of version control.
- Configure CORS to allow only the intended frontend origins in production.

## Future Improvements

- Expand the DSL with additional image transformations.
- Improve optimization passes and execution-cost estimation.
- Provide more detailed compiler diagnostics and execution traces.
- Add interactive visualization of intermediate representations.
- Expand automated testing and performance benchmarking.

## Learning Outcomes

This project demonstrates practical integration of:

- Compiler construction and language processing
- Abstract syntax trees and intermediate representations
- Semantic validation and optimization
- Image-processing algorithms
- REST API development
- React-based frontend development
- Automated testing and deployment workflows

## Author

**Ansh Gupta**  
B.Tech, Computer Science and Engineering — Data Science  
Vellore Institute of Technology, Vellore

## License

Add your preferred open-source license here if you intend to distribute the project under one.
