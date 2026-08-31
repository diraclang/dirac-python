<!-- TEST: cli_smoke -->
<!-- EXPECT: DIRAC Python says hi, World! -->
<dirac>
  <defvar name="name" value="World" />
  <output>DIRAC Python says hi, <variable name="name" />!</output>
</dirac>
