<!-- Exported subroutine chain -->

<subroutine name="install-local-ai"
            description="Install the local MLX/Qwen AI companion"
            visible="both"
            param-path="string:optional:Path to the dirac-llm checkout|~/diraclang/dirac-llm"
            param-dryRun="string:optional:Print planned commands instead of running them|true|false">
  <test-if test="${path}" eq="">
    <defvar name="path">~/diraclang/dirac-llm</defvar>
  </test-if>

  <test-if test="${dryRun}" eq="">
    <defvar name="dryRun">false</defvar>
  </test-if>

  <output>Installing local AI companion from <variable name="path" /></output>

  <test-if test="${dryRun}" eq="true">
    <output>Planned command: cd <variable name="path" /> &amp;&amp; bash setup.sh</output>
    <output>Next: source <variable name="path" />/.venv/bin/activate</output>
    <output>Next: python <variable name="path" />/mlx/python_script/stateless_chat_server_train_qwen.py</output>
  </test-if>

  <test-if test="${dryRun}" ne="true">
    <system>cd <variable name="path" /> &amp;&amp; bash setup.sh</system>
    <output>Setup complete.</output>
    <output>Next: source <variable name="path" />/.venv/bin/activate</output>
    <output>Next: python <variable name="path" />/mlx/python_script/stateless_chat_server_train_qwen.py</output>
  </test-if>
</subroutine>