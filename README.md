# SyntaxAI
## AI-Powered Diagram-to-Code Generator

SyntaxAI is an AI-powered application that converts software diagrams such as **flowcharts, UML diagrams, and architecture diagrams** into executable code.

The system uses a **vision-language AI model** to understand uploaded diagrams, analyze their structure, and generate code based on the detected components and relationships.

---

## 🚀 Features

- Upload software and architecture diagrams
- Convert diagrams into executable code
- Support for flowcharts, UML diagrams, and architecture diagrams
- AI-based diagram analysis
- Code generation from diagram structure
- Code refinement and improvement
- Security-focused code validation
- Code policy and rule checking
- Automatic fixing of detected code issues
- Backend API for processing requests
- Frontend interface for interacting with the system
- Local AI model support using Ollama
- Automated backend testing support

---

## 🏗️ System Architecture

SyntaxAI consists of three major components:

### 1. Frontend

The frontend provides the user interface where users can:

- Upload diagrams
- Submit diagram-processing requests
- View generated code
- Refine generated code
- Interact with the AI-powered code generation system

### 2. Backend

The backend handles:

- Diagram analysis
- AI model communication
- Code generation
- Code validation
- Code refinement
- Security checks
- API request processing
- Data storage and processing

### 3. AI Model

The system uses a local vision-language model through **Ollama**.

The model analyzes the uploaded diagram and extracts useful information that is then used for code generation.

---

## 🔄 Workflow

```text
User
  |
  v
Upload Diagram
  |
  v
Frontend
  |
  v
Backend API
  |
  v
Diagram Analysis
  |
  v
AI Vision-Language Model
  |
  v
Generate Code
  |
  v
Code Validation
  |
  v
Security / Policy Checks
  |
  v
Code Refinement
  |
  v
Generated Code


🛠️ Technologies Used
Frontend
HTML
CSS
JavaScript
Frontend web technologies
Backend
Python
API-based backend architecture
Python validation and processing modules
Artificial Intelligence
Ollama
Qwen2.5-VL vision-language model
Testing
Python testing framework
Automated backend test cases


📁 Project Structure
SyntaxAI/
│
├── app/
│   ├── __init__.py
│   ├── architecture.py
│   ├── bedrock_client.py
│   ├── errors.py
│   ├── guide.py
│   ├── handler.py
│   ├── pipeline.py
│   ├── store.py
│   ├── text_rules.py
│   ├── topology.py
│   │
│   ├── codegen/
│   │   ├── __init__.py
│   │   ├── cdk.py
│   │   ├── cloudformation.py
│   │   └── plan.py
│   │
│   ├── policy_engine/
│   │   ├── __init__.py
│   │   ├── code_rules.py
│   │   └── rules.py
│   │
│   ├── prompts/
│   │   ├── analyze.md
│   │   ├── fix.md
│   │   └── refine.md
│   │
│   └── validators/
│       ├── __init__.py
│       ├── cdk_validator.py
│       ├── cfn_validator.py
│       └── fixer.py
│
├── frontend/
│   └── frontend/
│       └── [frontend files]
│
├── tests/
│   ├── __init__.py
│   ├── helpers.py
│   ├── test_api.py
│   ├── test_architecture.py
│   ├── test_codegen.py
│   └── fixtures/
│       └── sample_analysis.json
│
├── local_server.py
├── requirements.txt
├── requirements-dev.txt
├── .env.example
├── .gitignore
└── README.md

⚙️ Installation
1. Clone the Repository
git clone https://github.com/likithbm/syntaxAI1.git
cd syntaxAI1
2. Create a Python Virtual Environment
python -m venv venv
3. Activate the Virtual Environment
Windows
venv\Scripts\activate
Linux / macOS
source venv/bin/activate
4. Install Dependencies
pip install -r requirements.txt

For development and testing:

pip install -r requirements-dev.txt
🤖 AI Model Setup

SyntaxAI can use a local vision-language model through Ollama.

Install Ollama and make sure the required model is available locally.

Example:

ollama pull qwen2.5-vl

Start the Ollama service before running the application.

🔐 Environment Configuration

Create a .env file based on the provided example:

.env.example

Configure the required environment variables according to your local setup.

Do not commit API keys, passwords, tokens, or other sensitive credentials to GitHub.

▶️ Running the Backend

Start the local backend server using:

python local_server.py

The backend will start locally and provide the required API endpoints for the frontend.

🌐 Running the Frontend

Navigate to the frontend directory:

cd frontend/frontend

Install the frontend dependencies if required and start the frontend development server using the project's configured command.

The frontend communicates with the backend to submit diagrams and display generated code.

🧠 Code Generation Pipeline

The code generation process consists of multiple stages.

Step 1: Diagram Input

The user uploads a diagram through the frontend.

Step 2: Diagram Analysis

The uploaded diagram is analyzed to identify:

Components
Nodes
Connections
Relationships
Architecture elements
Workflow structure
Step 3: AI Processing

The extracted diagram information is processed using the vision-language model.

Step 4: Code Generation

The system generates code according to the analyzed diagram structure.

Step 5: Validation

Generated code is checked using validation and policy rules.

Step 6: Refinement

Detected issues can be processed through the refinement and fixing pipeline.

Step 7: Output

The refined code is returned to the frontend for the user to view and use.

🔒 Security

SyntaxAI includes security-oriented processing for generated code.

The project contains:

Code policy rules
Validation modules
Code security checks
Automatic fixing support
Input validation
Secret and sensitive-data protection considerations

Sensitive configuration values should always be stored in environment variables rather than directly inside source code.

🧪 Testing

The project contains automated tests for important backend components.

Run the tests using:

pytest

The test suite includes testing for:

API functionality
Architecture processing
Code generation
Helper functionality
Validation logic
📌 Use Cases

SyntaxAI can be useful for:

Converting flowcharts into code
Converting UML diagrams into implementation structures
Converting architecture diagrams into infrastructure code
Rapid prototyping
Understanding software diagrams
Automating repetitive code generation
Assisting developers during system design
🔮 Future Enhancements

Possible future improvements include:

Support for additional programming languages
Support for more diagram formats
Improved diagram recognition
Support for additional AI models
Cloud-based model support
Real-time collaborative editing
Improved code testing and verification
Additional infrastructure-as-code formats
Enhanced frontend visualization
Deployment automation
👥 Team

SyntaxAI Team

This project was developed collaboratively as a team project.

📄 License

This project is intended for educational and project-development purposes.

Add an appropriate open-source license if the project is later released under a specific license.


**One important correction:** I kept the README based on the project information you provided. I did **not** add extra technologies/features that aren't supported by your supplied project details.

This is good to use as the main `README.md` in your GitHub repository.
  |
  v
Frontend Display
