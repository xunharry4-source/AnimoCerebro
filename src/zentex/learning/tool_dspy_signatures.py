import dspy

class ToolDistillationSignature(dspy.Signature):
    """
    Analyze the documentation and previous Sandbox evaluation feedback (if any) to distill a safe, correct cognitive tool.
    Constraints: The tool must be an internal cognitive aid, side-effect free.
    """
    doc_url = dspy.InputField(desc="Documentation URL of the cognitive tool to distill.")
    feedback_history = dspy.InputField(desc="Errors or constraints from previous sandbox evaluations. Fix these if present.", default="None")
    
    tool_name = dspy.OutputField(desc="Name of the tool as a string")
    description = dspy.OutputField(desc="Description of the tool as a string")
    usage_example = dspy.OutputField(desc="Usage example as a string")
    input_schema = dspy.OutputField(desc="Input schema as a valid JSON object string")
    output_schema = dspy.OutputField(desc="Output schema as a valid JSON object string")
    test_cases = dspy.OutputField(desc="List of test cases as a valid JSON array of objects with 'input' and 'expected' keys")

class ToolDistillationModule(dspy.Module):
    def __init__(self):
        super().__init__()
        # Use Chain of Thought for reasoning
        self.generate = dspy.ChainOfThought(ToolDistillationSignature)
        
    def forward(self, doc_url: str, feedback_history: str = "None"):
        prediction = self.generate(doc_url=doc_url, feedback_history=feedback_history)

class ToolCriticSignature(dspy.Signature):
    """
    Act as a strict code auditor. Review the generated tool schema and test cases.
    Ensure there are no infinite loops, missing fields, or unsafe system actions.
    """
    doc_url = dspy.InputField(desc="The original API documentation URL used as reference.")
    proposed_tool_name = dspy.InputField(desc="The generated tool name.")
    proposed_code_schema = dspy.InputField(desc="The generated schemas and descriptions.")
    proposed_test_cases = dspy.InputField(desc="The generated test cases.")
    
    is_approved = dspy.OutputField(desc="Boolean indicating if the tool structure is logical and safe. Exactly 'True' or 'False'.")
    critique_feedback = dspy.OutputField(desc="Explanation of issues found. If True, output 'Looks good'. If False, provide instructions to fix.")

class ToolCriticModule(dspy.Module):
    def __init__(self):
        super().__init__()
        self.critique = dspy.ChainOfThought(ToolCriticSignature)
        
    def forward(self, doc_url: str, proposed_tool_name: str, proposed_code_schema: str, proposed_test_cases: str):
        return self.critique(
            doc_url=doc_url, 
            proposed_tool_name=proposed_tool_name,
            proposed_code_schema=proposed_code_schema,
            proposed_test_cases=proposed_test_cases
        )
