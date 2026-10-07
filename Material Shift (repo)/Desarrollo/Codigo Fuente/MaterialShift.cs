// Material Shift v2.0 -- host de escritorio (WinForms + WebView2) del modelo de
// reasignación de materiales. La interfaz son dos páginas HTML (Model\app\sidebar.html y
// Model\app\dashboard.html); el cálculo lo hace el motor Python (Model\app\*.py), que
// corre como un proceso persistente (motor_servidor.py) para no pagar en cada clic el
// arranque de Python ni la lectura del Excel.
//
// Compilar: Desarrollo\Codigo Fuente\compilar.ps1  (csc.exe de .NET Framework 4.x, C# 5)
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

public static class Program
{
    [STAThread]
    public static void Main()
    {
        // WebView2's managed DLLs live in Model\bin (the root only holds the exe, like SimA).
        AppDomain.CurrentDomain.AssemblyResolve += (s, e) =>
        {
            string p = Path.Combine(Paths.Bin, new AssemblyName(e.Name).Name + ".dll");
            return File.Exists(p) ? Assembly.LoadFrom(p) : null;
        };
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Run();
    }

    // Kept separate so the JIT only touches WebView2 types after AssemblyResolve is hooked.
    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void Run()
    {
        Application.Run(new MaterialShiftForm());
    }
}

public static class Paths
{
    public static readonly string Base = AppDomain.CurrentDomain.BaseDirectory;
    public static readonly string Model = Path.Combine(Base, "Model");
    public static readonly string App = Path.Combine(Model, "app");
    public static readonly string Bin = Path.Combine(Model, "bin");
    public static readonly string Python = Path.Combine(Model, "python", "python.exe");
    public static readonly string Engine = Path.Combine(App, "ajuste_plan_ejecutable.py");
    public static readonly string Server = Path.Combine(App, "motor_servidor.py");
    public static readonly string Recursos = Path.Combine(Model, "recursos");
    public static readonly string Prefs = Path.Combine(Model, "Preferencias", "preferencias.json");
    public static readonly string Escenarios = Path.Combine(Base, "Escenarios");
    public static readonly string Inputs = Path.Combine(Base, "Inputs");
    public static readonly string Outputs = Path.Combine(Base, "Outputs");
    public static readonly string Local = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Material Shift");
    public static readonly string Cache = Path.Combine(Local, "cache");
    public static readonly string WebData = Path.Combine(Local, "WebView2");
}

public class PrioItem
{
    public string Id;
    public bool Active = true;
    public PrioItem(string id) { Id = id; }
    public PrioItem Clone() { var p = new PrioItem(Id); p.Active = Active; return p; }
}

// Objective criteria of ONE circuit (Desmonte and Mineral each have their own).
public class Crit
{
    public string Mode = "objetivo_fijo";
    public string Gran = "semanal";
    public string TolUnit = "Mt";
    public decimal Target, Tol, DailyTarget, DailyTol;
    public Crit(decimal target, decimal tol, decimal dailyTarget, decimal dailyTol)
    {
        Target = target; Tol = tol; DailyTarget = dailyTarget; DailyTol = dailyTol;
    }
    public double TolMt()
    {
        return TolUnit == "%" ? (double)Target * (double)Tol / 100.0 : (double)Tol;
    }
}

public class ProcResult
{
    public int ExitCode;
    public string Output;
}

// Persistent Python engine (Model\app\motor_servidor.py): one JSON request per line on
// stdin, one JSON answer per line on stdout. Requests are serialized. If the process
// cannot start or dies, the call falls back to a one-shot "python ajuste_plan_ejecutable.py".
public class MotorWorker : IDisposable
{
    private Process proc;
    private StreamWriter writer;
    private StreamReader reader;
    private int nextId = 1;
    private readonly SemaphoreSlim gate = new SemaphoreSlim(1, 1);
    private readonly JavaScriptSerializer json = new JavaScriptSerializer { MaxJsonLength = int.MaxValue };
    public bool UsedFallback;

    private bool Alive { get { return proc != null && !proc.HasExited; } }

    public void WarmUp()
    {
        Task.Run(() =>
        {
            gate.Wait();
            try { if (!Alive) Start(); }
            catch { }
            finally { gate.Release(); }
        });
    }

    private bool Start()
    {
        Kill();
        if (!File.Exists(Paths.Python) || !File.Exists(Paths.Server)) return false;
        var psi = new ProcessStartInfo
        {
            FileName = Paths.Python,
            Arguments = "-u " + MaterialShiftForm.QuoteArg(Paths.Server),
            UseShellExecute = false,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            StandardOutputEncoding = new UTF8Encoding(false),
            CreateNoWindow = true,
            WorkingDirectory = Paths.App
        };
        psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
        psi.EnvironmentVariables["PYTHONUTF8"] = "1";
        psi.EnvironmentVariables["MS_CACHE_DIR"] = Paths.Cache;
        proc = Process.Start(psi);
        writer = new StreamWriter(proc.StandardInput.BaseStream, new UTF8Encoding(false));
        writer.AutoFlush = true;
        reader = proc.StandardOutput;
        string line;
        while ((line = reader.ReadLine()) != null)
        {
            if (line.Contains("READY")) return true;
        }
        Kill();
        return false;
    }

    public Task<ProcResult> RunAsync(List<string> argv)
    {
        return Task.Run(() =>
        {
            gate.Wait();
            try { return RunLocked(argv); }
            finally { gate.Release(); }
        });
    }

    private ProcResult RunLocked(List<string> argv)
    {
        for (int attempt = 0; attempt < 2; attempt++)
        {
            try
            {
                if (!Alive && !Start()) break;
                int id = nextId++;
                var req = new Dictionary<string, object>();
                req["id"] = id;
                req["argv"] = argv;
                writer.WriteLine(json.Serialize(req));
                string line;
                while ((line = reader.ReadLine()) != null)
                {
                    if (!line.StartsWith("{")) continue;   // anything a library printed straight to the fd
                    Dictionary<string, object> ans;
                    try { ans = json.Deserialize<Dictionary<string, object>>(line); }
                    catch { continue; }
                    if (ans == null || !ans.ContainsKey("id") || ans["id"] == null || Convert.ToInt32(ans["id"]) != id) continue;
                    return new ProcResult { ExitCode = Convert.ToInt32(ans["rc"]), Output = Convert.ToString(ans["output"]) };
                }
                Kill();
            }
            catch
            {
                Kill();
            }
        }
        UsedFallback = true;
        var args = new StringBuilder(MaterialShiftForm.QuoteArg(Paths.Engine));
        foreach (var a in argv) args.Append(' ').Append(MaterialShiftForm.QuoteArg(a));
        return MaterialShiftForm.RunProcess(Paths.Python, args.ToString());
    }

    private void Kill()
    {
        try { if (proc != null && !proc.HasExited) proc.Kill(); } catch { }
        proc = null;
    }

    public void Dispose()
    {
        try
        {
            if (Alive)
            {
                writer.WriteLine("{\"cmd\":\"exit\"}");
                if (!proc.WaitForExit(1500)) proc.Kill();
            }
        }
        catch { }
        proc = null;
    }
}

public class SessionRun
{
    public string Id, Escenario, Fecha, Path, Json;
}

public class MaterialShiftForm : Form
{
    public const string Version = "v2.0";
    private const string AppTitle = "Material Shift";

    // ------------------------------------------------------------------ model
    private string input = "", output = "", sheet = "Plan_Base";
    private int activeYear = 2034;
    private readonly Crit des = new Crit(2.6M, 0.05M, 0.17M, 0.02M);
    private readonly Crit min = new Crit(1.0M, 0.05M, 0.15M, 0.02M);
    private readonly List<PrioItem> donorsC1 = new List<PrioItem>();
    private readonly List<PrioItem> donorsC2 = new List<PrioItem>();
    private readonly List<PrioItem> phasesC1 = new List<PrioItem>();
    private readonly List<PrioItem> phasesC2 = new List<PrioItem>();
    private readonly List<PrioItem> donorsMineral = new List<PrioItem>();
    private readonly List<PrioItem> phasesMineral = new List<PrioItem>();
    private List<string> detDonors = new List<string>(), detPhases = new List<string>(), detMineralDonors = new List<string>();
    private List<string> lastChancadoras = new List<string>();
    private List<string> lastCandidatos = new List<string>();
    private List<string> lastMateriales = new List<string>();
    private List<string> hojas = new List<string>();
    private Dictionary<string, Dictionary<string, string>> destinoConfig = new Dictionary<string, Dictionary<string, string>>();
    private bool configSheetUsed = false;
    private bool mineralDisponible = false;
    private List<string> mineralChancadoras = new List<string>();
    private List<string> mineralDonantes = new List<string>();
    private List<string> mineralMateriales = new List<string>();
    private Dictionary<string, HashSet<string>> materialBlocked = new Dictionary<string, HashSet<string>>();
    private Dictionary<string, HashSet<string>> defaultBlocked = new Dictionary<string, HashSet<string>>();

    // ------------------------------------------------------------------ session
    private string currentScenarioPath = null;
    private Dictionary<string, object> pendingScenario = null;
    private List<string> pendingMatrixRows = new List<string>();
    private string inputRelocated = null;
    private bool dirty = false, detecting = false, redetect = false, busy = false, hasResults = false, excelFresh = false, dark = false;
    private string statusText = "Listo.";
    private string circuit = "desmonte";
    private Dictionary<string, object> desmonteSummary = null, mineralSummary = null;
    private string lastResultsJson = null, lastDashboardHtml = null;
    private readonly List<SessionRun> sessionRuns = new List<SessionRun>();
    private readonly Dictionary<string, string> fileRuns = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
    private int runCounter = 0;
    private Dictionary<string, object> notice = null;
    private List<string> recent = new List<string>();
    private Dictionary<string, object> prefs = new Dictionary<string, object>();

    private readonly MotorWorker worker = new MotorWorker();
    private readonly SplitContainer split = new SplitContainer();
    private readonly WebView2 sideView = new WebView2();
    private readonly WebView2 dashView = new WebView2();
    private bool sideReady = false, dashReady = false;
    private FileSystemWatcher watcher;
    private readonly System.Windows.Forms.Timer watchTimer = new System.Windows.Forms.Timer { Interval = 700 };
    private string scenarioHash = null;
    private readonly JavaScriptSerializer json = new JavaScriptSerializer { MaxJsonLength = int.MaxValue };

    public MaterialShiftForm()
    {
        Text = AppTitle + " " + Version;
        Width = 1560;
        Height = 900;
        MinimumSize = new Size(940, 600);
        StartPosition = FormStartPosition.CenterScreen;
        KeyPreview = true;
        try { Icon = new Icon(Path.Combine(Paths.Recursos, "icono.ico")); } catch { }
        LoadPrefs();
        input = DefaultInput();
        output = DefaultOutput();
        BuildUi();
        ApplyTheme();
        RestoreWindow();
        UpdateTitle();
        FormClosing += OnFormClosing;
        watchTimer.Tick += (s, e) => { watchTimer.Stop(); CheckScenarioFile(); };
        worker.WarmUp();
    }

    // ================================================================== layout
    private void BuildUi()
    {
        split.Dock = DockStyle.Fill;
        split.FixedPanel = FixedPanel.Panel1;
        split.SplitterWidth = 5;
        Controls.Add(split);
        sideView.Dock = DockStyle.Fill;
        dashView.Dock = DockStyle.Fill;
        split.Panel1.Controls.Add(sideView);
        split.Panel2.Controls.Add(dashView);
        Shown += async (s, e) =>
        {
            try
            {
                split.Panel1MinSize = 360;
                split.Panel2MinSize = 480;
                split.SplitterDistance = Math.Max(360, Math.Min(620, PrefInt("sidebarWidth", 410)));
            }
            catch { }
            split.SplitterMoved += (s2, e2) => { prefs["sidebarWidth"] = split.SplitterDistance; };
            await InitWebViewsAsync();
        };
    }

    private async Task InitWebViewsAsync()
    {
        try
        {
            CoreWebView2Environment.SetLoaderDllFolderPath(Paths.Bin);
            Directory.CreateDirectory(Paths.WebData);
            var env = await CoreWebView2Environment.CreateAsync(null, Paths.WebData);
            await Task.WhenAll(sideView.EnsureCoreWebView2Async(env), dashView.EnsureCoreWebView2Async(env));
            foreach (var v in new[] { sideView, dashView })
            {
                var s = v.CoreWebView2.Settings;
                s.AreDefaultContextMenusEnabled = false;
                s.IsZoomControlEnabled = false;
                s.AreBrowserAcceleratorKeysEnabled = false;
                s.IsStatusBarEnabled = false;
                s.AreDevToolsEnabled = Environment.GetEnvironmentVariable("MS_DEVTOOLS") == "1";
            }
            sideView.CoreWebView2.WebMessageReceived += OnSideMessage;
            dashView.CoreWebView2.WebMessageReceived += OnDashMessage;
            sideView.CoreWebView2.Navigate(new Uri(Path.Combine(Paths.App, "sidebar.html")).AbsoluteUri);
            dashView.CoreWebView2.Navigate(new Uri(Path.Combine(Paths.App, "dashboard.html")).AbsoluteUri);
        }
        catch (Exception ex)
        {
            MessageBox.Show(this, "No se pudo iniciar la interfaz (WebView2): " + ex.Message, AppTitle, MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private void ApplyTheme()
    {
        Color bg = dark ? Color.FromArgb(11, 18, 27) : Color.FromArgb(238, 241, 245);
        BackColor = bg;
        split.BackColor = bg;
        sideView.DefaultBackgroundColor = bg;
        dashView.DefaultBackgroundColor = dark ? Color.FromArgb(14, 22, 33) : Color.FromArgb(243, 245, 248);
    }

    // ------------------------------------------------------------------ window helpers
    // WebView2 controls created while the window is minimized stay blank after it is
    // restored: re-showing them forces the controller to become visible again.
    private FormWindowState lastWindowState = FormWindowState.Normal;
    protected override void OnResize(EventArgs e)
    {
        base.OnResize(e);
        if (lastWindowState == FormWindowState.Minimized && WindowState != FormWindowState.Minimized)
        {
            foreach (var v in new[] { sideView, dashView }) { v.Visible = false; v.Visible = true; }
        }
        lastWindowState = WindowState;
    }

    protected override void OnShown(EventArgs e)
    {
        if (WindowState == FormWindowState.Minimized) WindowState = FormWindowState.Normal;
        base.OnShown(e);
    }

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern bool EnumThreadWindows(int threadId, EnumWindowsProc cb, IntPtr lParam);
    private delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    [System.Runtime.InteropServices.DllImport("kernel32.dll")]
    private static extern int GetCurrentThreadId();
    [System.Runtime.InteropServices.DllImport("user32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
    private static extern int GetClassName(IntPtr hWnd, StringBuilder name, int max);
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern IntPtr GetWindow(IntPtr hWnd, int cmd);
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern bool IsWindowVisible(IntPtr hWnd);
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern bool SetWindowPos(IntPtr hWnd, IntPtr after, int x, int y, int w, int h, uint flags);

    // Open/Save dialogs at a medium size, centered over the program (like SimA) instead
    // of wherever Windows last left them. The modal loop keeps WinForms timers running.
    private DialogResult ShowCentered(CommonDialog dlg)
    {
        int tries = 0;
        var timer = new System.Windows.Forms.Timer { Interval = 10 };
        timer.Tick += (s, e) =>
        {
            if (++tries > 300) { timer.Stop(); return; }
            IntPtr found = IntPtr.Zero;
            EnumThreadWindows(GetCurrentThreadId(), (h, l) =>
            {
                var sb = new StringBuilder(64);
                GetClassName(h, sb, 64);
                if (sb.ToString() == "#32770" && IsWindowVisible(h) && GetWindow(h, 4) == Handle) { found = h; return false; }
                return true;
            }, IntPtr.Zero);
            if (found == IntPtr.Zero) return;
            timer.Stop();
            var b = Bounds;
            int w = Math.Min(980, Math.Max(760, b.Width * 6 / 10)), hgt = Math.Min(640, Math.Max(480, b.Height * 7 / 10));
            SetWindowPos(found, IntPtr.Zero, b.X + (b.Width - w) / 2, b.Y + (b.Height - hgt) / 2, w, hgt, 0x0014);   // NOZORDER | NOACTIVATE
        };
        timer.Start();
        try { return dlg.ShowDialog(this); }
        finally { timer.Stop(); timer.Dispose(); RefocusPage(); }
    }

    // After a native dialog/message box closes, give the keyboard back to the page so the
    // shortcuts (F5, Ctrl+S...) keep working without an extra click.
    private void RefocusPage()
    {
        try { BeginInvoke((Action)(() => { Activate(); sideView.Focus(); })); } catch { }
    }

    private void UpdateTitle()
    {
        Text = AppTitle + " " + Version + "  —  " + ScenarioName() + (dirty ? " •" : "");
    }

    private string ScenarioName()
    {
        return string.IsNullOrEmpty(currentScenarioPath) ? "Sin título" : Path.GetFileNameWithoutExtension(currentScenarioPath);
    }

    private string DefaultInput()
    {
        string last = PrefStr("lastInput", null);
        if (!string.IsNullOrEmpty(last) && File.Exists(last)) return last;
        try
        {
            var f = Directory.Exists(Paths.Inputs) ? Directory.GetFiles(Paths.Inputs, "*.xlsx").OrderBy(x => x).FirstOrDefault() : null;
            if (f != null) return f;
        }
        catch { }
        return "";
    }

    private static string DefaultOutput() { return Path.Combine(Paths.Outputs, "Resultado.xlsx"); }

    // ================================================================== preferences
    private void LoadPrefs()
    {
        try
        {
            if (File.Exists(Paths.Prefs))
                prefs = json.Deserialize<Dictionary<string, object>>(File.ReadAllText(Paths.Prefs, Encoding.UTF8)) ?? new Dictionary<string, object>();
        }
        catch { prefs = new Dictionary<string, object>(); }
        dark = prefs.ContainsKey("dark") && prefs["dark"] is bool && (bool)prefs["dark"];
        recent = ToStringList(prefs.ContainsKey("recent") ? prefs["recent"] : null).Where(File.Exists).ToList();
    }

    private void SavePrefs()
    {
        try
        {
            prefs["dark"] = dark;
            prefs["recent"] = recent;
            if (!string.IsNullOrEmpty(input) && File.Exists(input)) prefs["lastInput"] = input;
            var b = WindowState == FormWindowState.Normal ? Bounds : RestoreBounds;
            prefs["bounds"] = new Dictionary<string, object> { { "x", b.X }, { "y", b.Y }, { "w", b.Width }, { "h", b.Height }, { "max", WindowState == FormWindowState.Maximized } };
            Directory.CreateDirectory(Path.GetDirectoryName(Paths.Prefs));
            File.WriteAllText(Paths.Prefs, json.Serialize(prefs), new UTF8Encoding(false));
        }
        catch { }
    }

    private void RestoreWindow()
    {
        var b = prefs.ContainsKey("bounds") ? prefs["bounds"] as Dictionary<string, object> : null;
        if (b == null) return;
        try
        {
            var r = new Rectangle(Convert.ToInt32(b["x"]), Convert.ToInt32(b["y"]), Convert.ToInt32(b["w"]), Convert.ToInt32(b["h"]));
            if (Screen.AllScreens.Any(s => s.WorkingArea.IntersectsWith(r)) && r.Width >= MinimumSize.Width && r.Height >= MinimumSize.Height)
            {
                StartPosition = FormStartPosition.Manual;
                Bounds = r;
            }
            if (b.ContainsKey("max") && b["max"] is bool && (bool)b["max"]) WindowState = FormWindowState.Maximized;
        }
        catch { }
    }

    private int PrefInt(string k, int def) { try { return prefs.ContainsKey(k) ? Convert.ToInt32(prefs[k]) : def; } catch { return def; } }
    private string PrefStr(string k, string def) { return prefs.ContainsKey(k) && prefs[k] != null ? Convert.ToString(prefs[k]) : def; }

    private void AddRecent(string path)
    {
        if (string.IsNullOrEmpty(path)) return;
        recent.RemoveAll(p => string.Equals(p, path, StringComparison.OrdinalIgnoreCase));
        recent.Insert(0, path);
        if (recent.Count > 10) recent.RemoveRange(10, recent.Count - 10);
        SavePrefs();
    }

    private List<object> RecentForUi()
    {
        var list = new List<object>();
        foreach (var p in recent)
        {
            var d = new Dictionary<string, object>();
            d["path"] = p;
            d["name"] = Path.GetFileNameWithoutExtension(p);
            d["folder"] = Path.GetFileName(Path.GetDirectoryName(p));
            list.Add(d);
        }
        return list;
    }

    // ================================================================== closing
    private void OnFormClosing(object sender, FormClosingEventArgs e)
    {
        // Only asks when something actually changed (just navigating never asks).
        if (dirty)
        {
            var choice = MessageBox.Show(this, "El escenario «" + ScenarioName() + "» tiene cambios sin guardar.\n\n¿Deseas guardarlos antes de salir?",
                AppTitle, MessageBoxButtons.YesNoCancel, MessageBoxIcon.Warning);
            if (choice == DialogResult.Cancel) { e.Cancel = true; RefocusPage(); return; }
            if (choice == DialogResult.Yes && !SaveScenario(false)) { e.Cancel = true; RefocusPage(); return; }
        }
        SavePrefs();
        if (watcher != null) watcher.Dispose();
        worker.Dispose();
    }

    // ================================================================== change tracking
    private void MarkChanged()
    {
        dirty = true;
        excelFresh = false;
        UpdateTitle();
        if (hasResults) PostDash(Msg("stale", "text", "La configuración cambió después de este cálculo. Presiona F5 para recalcular."));
    }

    private void SetStatus(string text)
    {
        statusText = text;
        PushStatus();
    }

    private void SetBusy(bool on, string text)
    {
        busy = on;
        statusText = text;
        PushStatus();
    }

    private bool CalcEnabled { get { return !busy && !detecting && File.Exists(input); } }
    private bool ExcelEnabled { get { return !busy && hasResults; } }

    // ================================================================== scenario CSV (v3)
    // Plain sections in square brackets with "name;value" rows. [Objetivos] is a small
    // table with one column per circuit; v1/v2 files (one shared column) still open.
    private Dictionary<string, object> BlockedOut()
    {
        var blocked = new Dictionary<string, object>();
        foreach (var kv in materialBlocked)
            if (kv.Value.Count > 0) blocked[kv.Key] = kv.Value.OrderBy(x => x).Cast<object>().ToList();
        return blocked;
    }

    private Dictionary<string, object> DestinoConfigOut()
    {
        var o = new Dictionary<string, object>();
        foreach (var kv in destinoConfig)
        {
            var row = new Dictionary<string, object>();
            row["destino"] = kv.Value.ContainsKey("destino") ? kv.Value["destino"] : "N/A";
            row["material"] = kv.Value.ContainsKey("material") ? kv.Value["material"] : "N/A";
            o[kv.Key] = row;
        }
        return o;
    }

    private static List<object> PrioToList(List<PrioItem> items)
    {
        var list = new List<object>();
        foreach (var it in items)
        {
            var o = new Dictionary<string, object>();
            o["id"] = it.Id;
            o["active"] = it.Active;
            list.Add(o);
        }
        return list;
    }

    private static string CsvQ(string v)
    {
        if (v == null) return "";
        if (v.IndexOfAny(new char[] { ';', '"', '\n', '\r' }) >= 0) return "\"" + v.Replace("\"", "\"\"") + "\"";
        return v;
    }

    private static string Dec(decimal v, int places)
    {
        return v.ToString("0." + new string('0', places), System.Globalization.CultureInfo.InvariantCulture);
    }

    private static string ModeText(string m) { return m == "balanceado" ? "Balanceado" : "Objetivo fijo"; }
    private static string GranText(string g) { return g == "diario" ? "Diario" : "Semanal"; }

    private string BuildScenarioCsv()
    {
        var sb = new StringBuilder();
        Action<string[]> row = cells => sb.Append(string.Join(";", cells.Select(CsvQ))).Append("\r\n");
        sb.Append("sep=;\r\n");
        row(new[] { "Escenario Material Shift", "version 3" });
        row(new[] { "Puedes editar los valores en Excel. No cambies los nombres de las secciones entre corchetes." });
        sb.Append("\r\n[General]\r\n");
        row(new[] { "Archivo base", input });
        row(new[] { "Archivo de salida", output });
        row(new[] { "Hoja", sheet });
        row(new[] { "Año activo", activeYear.ToString() });
        sb.Append("\r\n[Objetivos]\r\n");
        row(new[] { "Parámetro", "Desmonte", "Mineral" });
        row(new[] { "Modo", ModeText(des.Mode), ModeText(min.Mode) });
        row(new[] { "Granularidad", GranText(des.Gran), GranText(min.Gran) });
        row(new[] { "Objetivo Mt/sem", Dec(des.Target, 2), Dec(min.Target, 2) });
        row(new[] { "Tolerancia", Dec(des.Tol, 2), Dec(min.Tol, 2) });
        row(new[] { "Unidad de tolerancia", des.TolUnit, min.TolUnit });
        row(new[] { "Objetivo Mt/día", Dec(des.DailyTarget, 3), Dec(min.DailyTarget, 3) });
        row(new[] { "Tolerancia diaria Mt", Dec(des.DailyTol, 3), Dec(min.DailyTol, 3) });

        string c1 = lastChancadoras.Count > 0 ? lastChancadoras[0] : "Chancadora 1";
        string c2 = lastChancadoras.Count > 1 ? lastChancadoras[1] : "Chancadora 2";
        AppendPrioSection(sb, "Donantes 1", c1, donorsC1);
        AppendPrioSection(sb, "Donantes 2", c2, donorsC2);
        AppendPrioSection(sb, "Fases 1", c1, phasesC1);
        AppendPrioSection(sb, "Fases 2", c2, phasesC2);
        if (mineralChancadoras.Count > 0)
        {
            string cm = string.Join(", ", mineralChancadoras);
            AppendPrioSection(sb, "Donantes Mineral", cm, donorsMineral);
            AppendPrioSection(sb, "Fases Mineral", cm, phasesMineral);
        }
        if (destinoConfig.Count > 0)
        {
            sb.Append("\r\n[Config Destinos]\r\n");
            row(new[] { "Nota", "Receptor/Donante/N.A. y Mineral/Desmonte/N.A. por destino (hoja Config del Excel o editado en la app)" });
            row(new[] { "Destino", "Config_Destinos", "Config_Materiales" });
            foreach (var kv in destinoConfig)
                row(new[] { kv.Key, kv.Value.ContainsKey("destino") ? kv.Value["destino"] : "N/A", kv.Value.ContainsKey("material") ? kv.Value["material"] : "N/A" });
        }
        AppendMatrix(sb, "Materiales", lastChancadoras.Concat(donorsC1.Select(d => d.Id)).ToList(), lastMateriales);
        if (mineralChancadoras.Count > 0) AppendMatrix(sb, "Materiales Mineral", mineralChancadoras.Concat(mineralDonantes).ToList(), mineralMateriales);
        return sb.ToString();
    }

    private void AppendMatrix(StringBuilder sb, string section, List<string> dests, List<string> mats)
    {
        if (mats.Count == 0) return;
        sb.Append("\r\n[").Append(section).Append("]\r\n");
        sb.Append("Nota;\"1 = ese destino puede recibir y entregar ese material; 0 = ese material no se toca en ese destino\"\r\n");
        sb.Append("Destino;").Append(string.Join(";", mats.Select(CsvQ))).Append("\r\n");
        foreach (var dest in dests)
        {
            HashSet<string> set;
            materialBlocked.TryGetValue(dest, out set);
            sb.Append(CsvQ(dest));
            foreach (var m in mats) sb.Append(";").Append(set != null && set.Contains(m) ? "0" : "1");
            sb.Append("\r\n");
        }
    }

    private static void AppendPrioSection(StringBuilder sb, string section, string crusher, List<PrioItem> items)
    {
        sb.Append("\r\n[").Append(section).Append("]\r\n");
        sb.Append("Chancadora;").Append(CsvQ(crusher)).Append("\r\n");
        sb.Append("Orden;Columna;Usar\r\n");
        for (int i = 0; i < items.Count; i++)
            sb.Append(i + 1).Append(";").Append(CsvQ(items[i].Id)).Append(";").Append(items[i].Active ? "Si" : "No").Append("\r\n");
    }

    private static string Norm(string s)
    {
        if (s == null) return "";
        string d = s.Trim().ToLowerInvariant().Normalize(NormalizationForm.FormD);
        var sb = new StringBuilder();
        foreach (char c in d)
            if (System.Globalization.CharUnicodeInfo.GetUnicodeCategory(c) != System.Globalization.UnicodeCategory.NonSpacingMark) sb.Append(c);
        return sb.ToString();
    }

    private static string[] SplitCsvLine(string line, char delim)
    {
        var cells = new List<string>();
        var cur = new StringBuilder();
        bool inQ = false;
        for (int i = 0; i < line.Length; i++)
        {
            char c = line[i];
            if (inQ)
            {
                if (c == '"')
                {
                    if (i + 1 < line.Length && line[i + 1] == '"') { cur.Append('"'); i++; }
                    else inQ = false;
                }
                else cur.Append(c);
            }
            else if (c == '"') inQ = true;
            else if (c == delim) { cells.Add(cur.ToString()); cur.Clear(); }
            else cur.Append(c);
        }
        cells.Add(cur.ToString());
        return cells.ToArray();
    }

    public static Dictionary<string, object> ParseScenarioCsv(string text, List<string> matrixRows)
    {
        text = text.TrimStart('﻿');
        string[] lines = text.Replace("\r\n", "\n").Replace('\r', '\n').Split('\n');
        char delim = text.Contains(";") ? ';' : ',';   // Excel re-saves with the regional separator
        var general = new Dictionary<string, string>();
        var mineralCol = new Dictionary<string, string>();
        var lists = new Dictionary<string, List<KeyValuePair<int, PrioItem>>>();
        var matrixHead = new Dictionary<string, string[]>();
        var matrixBody = new Dictionary<string, List<string[]>>();
        var destinoConfigRows = new Dictionary<string, Dictionary<string, object>>();
        string section = "";
        bool sawScenario = false, objTable = false;

        foreach (var raw in lines)
        {
            string line = raw.Trim();
            if (line.Length == 0 || line.Trim(delim, ' ').Length == 0) continue;
            if (line.StartsWith("sep=", StringComparison.OrdinalIgnoreCase)) continue;
            if (line.StartsWith("["))
            {
                int close = line.IndexOf(']');
                section = Norm(line.Substring(1, (close > 0 ? close : line.Length) - 1));
                continue;
            }
            string[] cells = SplitCsvLine(line, delim);
            if (cells.Length == 0) continue;
            string c0 = Norm(cells[0]);
            if (section == "" && (c0.StartsWith("escenario ajuste plan") || c0.StartsWith("escenario material shift"))) { sawScenario = true; continue; }
            switch (section)
            {
                case "general":
                    if (cells.Length >= 2) general[c0] = cells[1].Trim();
                    break;
                case "objetivos":
                    if (c0 == "parametro") { objTable = true; break; }
                    if (cells.Length >= 2) general[c0] = cells[1].Trim();
                    if (objTable && cells.Length >= 3 && cells[2].Trim().Length > 0) mineralCol[c0] = cells[2].Trim();
                    break;
                case "donantes 1": case "donantes 2": case "fases 1": case "fases 2": case "donantes mineral": case "fases mineral":
                    int order;
                    if (cells.Length >= 2 && int.TryParse(cells[0].Trim(), out order) && cells[1].Trim().Length > 0)
                    {
                        var it = new PrioItem(cells[1].Trim());
                        it.Active = cells.Length < 3 || Norm(cells[2]) != "no";
                        List<KeyValuePair<int, PrioItem>> list;
                        if (!lists.TryGetValue(section, out list)) { list = new List<KeyValuePair<int, PrioItem>>(); lists[section] = list; }
                        list.Add(new KeyValuePair<int, PrioItem>(order, it));
                    }
                    break;
                case "materiales": case "materiales mineral":
                    if (c0 == "destino") { matrixHead[section] = cells; matrixBody[section] = new List<string[]>(); }
                    else if (c0 != "nota" && matrixHead.ContainsKey(section) && cells[0].Trim().Length > 0) matrixBody[section].Add(cells);
                    break;
                case "config destinos":
                    if (c0 != "destino" && c0 != "nota" && cells[0].Trim().Length > 0 && cells.Length >= 3)
                    {
                        var r = new Dictionary<string, object>();
                        r["destino"] = cells[1].Trim();
                        r["material"] = cells[2].Trim();
                        destinoConfigRows[cells[0].Trim()] = r;
                    }
                    break;
            }
        }
        if (!sawScenario && general.Count == 0) return null;

        Func<Dictionary<string, string>, string, string> g = (src, k) => src.ContainsKey(k) ? src[k] : null;
        Func<Dictionary<string, string>, string, string> num = (src, k) => g(src, k) == null ? null : g(src, k).Replace(',', '.');
        var d = new Dictionary<string, object>();
        d["version"] = objTable ? 3 : 2;
        if (g(general, "archivo base") != null) d["input"] = g(general, "archivo base");
        if (g(general, "archivo de salida") != null) d["output"] = g(general, "archivo de salida");
        if (g(general, "hoja") != null) d["sheet"] = g(general, "hoja");
        if (num(general, "ano activo") != null) d["activeYear"] = num(general, "ano activo");
        d["mode"] = g(general, "modo") != null && Norm(g(general, "modo")).StartsWith("balanc") ? "balanceado" : "objetivo_fijo";
        if (num(general, "objetivo mt/sem") != null) d["target"] = num(general, "objetivo mt/sem");
        if (num(general, "tolerancia") != null) d["tolerance"] = num(general, "tolerancia");
        d["toleranceUnit"] = g(general, "unidad de tolerancia") == "%" ? "%" : "Mt";
        d["granularity"] = g(general, "granularidad") != null && Norm(g(general, "granularidad")).StartsWith("diar") ? "diario" : "semanal";
        if (num(general, "objetivo mt/dia") != null) d["dailyTarget"] = num(general, "objetivo mt/dia");
        if (num(general, "tolerancia diaria mt") != null) d["dailyTolerance"] = num(general, "tolerancia diaria mt");
        if (objTable)
        {
            if (g(mineralCol, "modo") != null) d["mineralMode"] = Norm(g(mineralCol, "modo")).StartsWith("balanc") ? "balanceado" : "objetivo_fijo";
            if (g(mineralCol, "granularidad") != null) d["mineralGranularity"] = Norm(g(mineralCol, "granularidad")).StartsWith("diar") ? "diario" : "semanal";
            if (num(mineralCol, "objetivo mt/sem") != null) d["mineralTarget"] = num(mineralCol, "objetivo mt/sem");
            if (num(mineralCol, "tolerancia") != null) d["mineralTolerance"] = num(mineralCol, "tolerancia");
            if (g(mineralCol, "unidad de tolerancia") != null) d["mineralToleranceUnit"] = g(mineralCol, "unidad de tolerancia") == "%" ? "%" : "Mt";
            if (num(mineralCol, "objetivo mt/dia") != null) d["mineralDailyTarget"] = num(mineralCol, "objetivo mt/dia");
            if (num(mineralCol, "tolerancia diaria mt") != null) d["mineralDailyTolerance"] = num(mineralCol, "tolerancia diaria mt");
        }
        else
        {
            // v2: one shared column plus two Mineral rows.
            if (num(general, "objetivo mt/sem mineral") != null) d["mineralTarget"] = num(general, "objetivo mt/sem mineral");
            if (num(general, "tolerancia mineral") != null) d["mineralTolerance"] = num(general, "tolerancia mineral");
        }

        string[][] map = {
            new[] { "donantes 1", "donorsC1" }, new[] { "donantes 2", "donorsC2" },
            new[] { "fases 1", "phasesC1" }, new[] { "fases 2", "phasesC2" },
            new[] { "donantes mineral", "donorsMineral" }, new[] { "fases mineral", "phasesMineral" } };
        foreach (var pair in map)
        {
            List<KeyValuePair<int, PrioItem>> list;
            if (!lists.TryGetValue(pair[0], out list) || list.Count == 0) continue;
            d[pair[1]] = list.OrderBy(x => x.Key).Select(kv => (object)new Dictionary<string, object> { { "id", kv.Value.Id }, { "active", kv.Value.Active } }).ToList();
        }
        if (matrixHead.Count > 0)
        {
            var blocked = new Dictionary<string, object>();
            foreach (var sec in matrixHead.Keys)
            {
                var head = matrixHead[sec];
                foreach (var r in matrixBody[sec])
                {
                    if (matrixRows != null) matrixRows.Add(r[0].Trim());
                    var mats = new List<object>();
                    for (int j = 1; j < head.Length && j < r.Length; j++)
                    {
                        string v = Norm(r[j]);
                        if (v == "0" || v == "no" || v == "false") mats.Add(head[j].Trim());
                    }
                    if (mats.Count > 0) blocked[r[0].Trim()] = mats;
                }
            }
            d["materialBlocked"] = blocked;
        }
        if (destinoConfigRows.Count > 0)
        {
            var dc = new Dictionary<string, object>();
            foreach (var kv in destinoConfigRows) dc[kv.Key] = kv.Value;
            d["destinoConfig"] = dc;
        }
        return d;
    }

    private static string SVal(Dictionary<string, object> d, string key)
    {
        return d != null && d.ContainsKey(key) && d[key] != null ? d[key].ToString() : null;
    }

    private static decimal Clamp(decimal v) { return v < 0 ? 0 : v > 99 ? 99 : v; }

    private static bool TryDec(object o, out decimal v)
    {
        v = 0;
        if (o == null) return false;
        return decimal.TryParse(o.ToString().Replace(',', '.'), System.Globalization.NumberStyles.Any, System.Globalization.CultureInfo.InvariantCulture, out v);
    }

    private static void SetDec(ref decimal field, Dictionary<string, object> d, string key)
    {
        decimal v;
        if (d.ContainsKey(key) && TryDec(d[key], out v)) field = Clamp(v);
    }

    private void ApplyScenarioScalars(Dictionary<string, object> d)
    {
        if (SVal(d, "input") != null) input = SVal(d, "input");
        if (SVal(d, "output") != null) output = SVal(d, "output");
        if (SVal(d, "sheet") != null) sheet = SVal(d, "sheet");
        des.Mode = SVal(d, "mode") == "balanceado" ? "balanceado" : "objetivo_fijo";
        des.Gran = SVal(d, "granularity") == "diario" ? "diario" : "semanal";
        des.TolUnit = SVal(d, "toleranceUnit") == "%" ? "%" : "Mt";
        SetDec(ref des.Target, d, "target");
        SetDec(ref des.Tol, d, "tolerance");
        SetDec(ref des.DailyTarget, d, "dailyTarget");
        SetDec(ref des.DailyTol, d, "dailyTolerance");
        // A scenario without its own Mineral criteria (v19 files) keeps v19's behaviour:
        // Mineral shared Desmonte's mode, granularity, unit and daily values.
        min.Mode = SVal(d, "mineralMode") ?? des.Mode;
        min.Gran = SVal(d, "mineralGranularity") ?? des.Gran;
        min.TolUnit = SVal(d, "mineralToleranceUnit") ?? des.TolUnit;
        min.DailyTarget = des.DailyTarget;
        min.DailyTol = des.DailyTol;
        SetDec(ref min.Target, d, "mineralTarget");
        SetDec(ref min.Tol, d, "mineralTolerance");
        SetDec(ref min.DailyTarget, d, "mineralDailyTarget");
        SetDec(ref min.DailyTol, d, "mineralDailyTolerance");
        input = ResolveInput(input, currentScenarioPath);
    }

    // A scenario saved on another PC/folder may point to an Excel that does not exist
    // here: look for the same file name next to the scenario and in Inputs\.
    private string ResolveInput(string path, string scenarioPath)
    {
        inputRelocated = null;
        if (string.IsNullOrEmpty(path) || File.Exists(path)) return path;
        string name = Path.GetFileName(path);
        var candidates = new List<string>();
        if (!string.IsNullOrEmpty(scenarioPath)) candidates.Add(Path.Combine(Path.GetDirectoryName(scenarioPath), name));
        candidates.Add(Path.Combine(Paths.Inputs, name));
        foreach (var c in candidates)
            if (File.Exists(c)) { inputRelocated = path; return c; }
        return path;
    }

    private static List<PrioItem> ReadPrio(Dictionary<string, object> d, string key)
    {
        if (!d.ContainsKey(key)) return null;
        var items = d[key] as System.Collections.IEnumerable;
        if (items == null) return null;
        var list = new List<PrioItem>();
        foreach (var o in items)
        {
            var dict = o as Dictionary<string, object>;
            if (dict == null || !dict.ContainsKey("id")) continue;
            var it = new PrioItem(dict["id"].ToString());
            if (dict.ContainsKey("active") && dict["active"] is bool) it.Active = (bool)dict["active"];
            list.Add(it);
        }
        return list;
    }

    private static void ReplaceList(List<PrioItem> target, List<PrioItem> source)
    {
        if (source == null || source.Count == 0) return;
        target.Clear();
        target.AddRange(source);
    }

    // Applies the lists saved in a scenario on top of what detection found.
    private void ApplyPendingScenario()
    {
        if (pendingScenario == null) return;
        var d = pendingScenario;
        pendingScenario = null;
        int y;
        if (SVal(d, "activeYear") != null && int.TryParse(SVal(d, "activeYear").Split('.')[0], out y) && y >= 2000 && y <= 2100) activeYear = y;
        ReplaceList(donorsC1, ReadPrio(d, "donorsC1"));
        ReplaceList(donorsC2, ReadPrio(d, "donorsC2"));
        ReplaceList(phasesC1, ReadPrio(d, "phasesC1"));
        ReplaceList(phasesC2, ReadPrio(d, "phasesC2"));
        ReplaceList(donorsMineral, ReadPrio(d, "donorsMineral"));
        ReplaceList(phasesMineral, ReadPrio(d, "phasesMineral"));
        var mb = d.ContainsKey("materialBlocked") ? d["materialBlocked"] as Dictionary<string, object> : null;
        if (mb != null)
        {
            if (pendingMatrixRows.Count == 0)
            {
                // JSON scenario (v19): the saved table replaces everything, as before.
                materialBlocked = new Dictionary<string, HashSet<string>>();
            }
            else
            {
                // CSV: every destino listed in the file takes the file's row (all 1s = no
                // restrictions); destinos the file doesn't list keep their defaults.
                foreach (var dest in pendingMatrixRows) materialBlocked.Remove(dest);
            }
            foreach (var kv in mb) materialBlocked[kv.Key] = new HashSet<string>(ToStringList(kv.Value));
        }
        pendingMatrixRows = new List<string>();
        var restored = ParseDestinoConfigDict(d.ContainsKey("destinoConfig") ? d["destinoConfig"] as Dictionary<string, object> : null);
        if (restored != null) destinoConfig = restored;
        dirty = false;
        UpdateTitle();
        PushState();
        SetStatus("Escenario cargado: " + ScenarioName() + (inputRelocated != null ? "  ·  El archivo base no estaba en la ruta guardada; se usó " + input : ""));
    }

    private static Dictionary<string, Dictionary<string, string>> ParseDestinoConfigDict(Dictionary<string, object> dc)
    {
        if (dc == null || dc.Count == 0) return null;
        var result = new Dictionary<string, Dictionary<string, string>>();
        foreach (var kv in dc)
        {
            var cfg = kv.Value as Dictionary<string, object>;
            if (cfg == null) continue;
            var row = new Dictionary<string, string>();
            row["destino"] = cfg.ContainsKey("destino") ? Convert.ToString(cfg["destino"]) : "N/A";
            row["material"] = cfg.ContainsKey("material") ? Convert.ToString(cfg["material"]) : "N/A";
            result[kv.Key] = row;
        }
        return result.Count > 0 ? result : null;
    }

    private void NewScenario()
    {
        if (!ConfirmDiscard()) return;
        currentScenarioPath = null;
        pendingScenario = null;
        des.Mode = "objetivo_fijo"; des.Gran = "semanal"; des.TolUnit = "Mt"; des.Target = 2.6M; des.Tol = 0.05M; des.DailyTarget = 0.17M; des.DailyTol = 0.02M;
        min.Mode = "objetivo_fijo"; min.Gran = "semanal"; min.TolUnit = "Mt"; min.Target = 1.0M; min.Tol = 0.05M; min.DailyTarget = 0.15M; min.DailyTol = 0.02M;
        destinoConfig = new Dictionary<string, Dictionary<string, string>>();
        output = DefaultOutput();
        notice = null;
        WatchScenario();
        dirty = false;
        UpdateTitle();
        DetectColumnsAsync();
        SetStatus("Nuevo escenario con valores por defecto.");
    }

    private bool ConfirmDiscard()
    {
        if (!dirty) return true;
        var r = MessageBox.Show(this, "El escenario «" + ScenarioName() + "» tiene cambios sin guardar.\n\n¿Deseas guardarlos?", AppTitle, MessageBoxButtons.YesNoCancel, MessageBoxIcon.Warning);
        RefocusPage();
        if (r == DialogResult.Cancel) return false;
        if (r == DialogResult.Yes) return SaveScenario(false);
        return true;
    }

    private bool SaveScenario(bool asNew)
    {
        string path = currentScenarioPath;
        if (path != null && !path.EndsWith(".csv", StringComparison.OrdinalIgnoreCase)) asNew = true;   // old .txt/.json -> save as .csv
        if (asNew || string.IsNullOrEmpty(path))
        {
            using (var dlg = new SaveFileDialog())
            {
                dlg.Filter = "Escenario Material Shift (*.csv)|*.csv";
                dlg.DefaultExt = "csv";
                dlg.InitialDirectory = path != null ? Path.GetDirectoryName(path) : EnsureDir(Paths.Escenarios);
                dlg.FileName = path != null ? Path.GetFileNameWithoutExtension(path) + ".csv" : "Escenario.csv";
                if (ShowCentered(dlg) != DialogResult.OK) return false;
                path = dlg.FileName;
            }
        }
        // A new scenario still using the default output gets its own Excel name.
        if (string.Equals(output, DefaultOutput(), StringComparison.OrdinalIgnoreCase))
            output = Path.Combine(Paths.Outputs, Path.GetFileNameWithoutExtension(path) + ".xlsx");
        try
        {
            File.WriteAllText(path, BuildScenarioCsv(), new UTF8Encoding(true));   // BOM: Excel and Notepad show accents correctly
            scenarioHash = HashBytes(File.ReadAllBytes(path));
        }
        catch (Exception ex)
        {
            MessageBox.Show(this, ex.Message + "\n\nSi el archivo está abierto en Excel, ciérralo e intenta de nuevo.", "No se pudo guardar el escenario", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return false;
        }
        currentScenarioPath = path;
        dirty = false;
        notice = null;
        AddRecent(path);
        WatchScenario();
        UpdateTitle();
        PushState();
        SetStatus("Escenario guardado: " + path);
        return true;
    }

    private void OpenScenario()
    {
        if (!ConfirmDiscard()) return;
        using (var dlg = new OpenFileDialog())
        {
            dlg.Filter = "Escenarios (*.csv;*.txt;*.json)|*.csv;*.txt;*.json|Todos los archivos (*.*)|*.*";
            dlg.InitialDirectory = currentScenarioPath != null ? Path.GetDirectoryName(currentScenarioPath) : EnsureDir(Paths.Escenarios);
            if (ShowCentered(dlg) != DialogResult.OK) return;
            OpenScenarioFile(dlg.FileName, false);
        }
    }

    // fromNotice: the user accepted the "scenario changed outside" notice. Results already
    // on screen are kept either way (they are marked as belonging to the previous run).
    private void OpenScenarioFile(string path, bool fromNotice)
    {
        if (!File.Exists(path))
        {
            MessageBox.Show(this, "No se encontró el archivo:\n" + path, AppTitle);
            recent.RemoveAll(p => string.Equals(p, path, StringComparison.OrdinalIgnoreCase));
            SavePrefs();
            PushState();
            return;
        }
        Dictionary<string, object> data;
        var rows = new List<string>();
        try
        {
            string text = ReadShared(path);
            if (text.TrimStart('﻿', ' ', '\r', '\n', '\t').StartsWith("{")) data = json.Deserialize<Dictionary<string, object>>(text);
            else data = ParseScenarioCsv(text, rows);
        }
        catch (Exception ex)
        {
            MessageBox.Show(this, ex.Message + "\n\nSi el archivo está abierto en Excel, ciérralo e intenta de nuevo.", "No se pudo abrir el escenario", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return;
        }
        if (data == null || !data.ContainsKey("version"))
        {
            MessageBox.Show(this, "El archivo no parece un escenario de Material Shift.", AppTitle);
            return;
        }
        currentScenarioPath = path;
        try { scenarioHash = HashBytes(ReadSharedBytes(path)); } catch { }
        ApplyScenarioScalars(data);
        var restored = ParseDestinoConfigDict(data.ContainsKey("destinoConfig") ? data["destinoConfig"] as Dictionary<string, object> : null);
        destinoConfig = restored ?? new Dictionary<string, Dictionary<string, string>>();
        pendingScenario = data;
        pendingMatrixRows = rows;
        notice = null;
        AddRecent(path);
        WatchScenario();
        dirty = false;
        UpdateTitle();
        if (hasResults) PostDash(Msg("stale", "text", fromNotice
            ? "El escenario se actualizó desde el archivo. Los resultados mostrados son de la corrida anterior: presiona F5 para recalcular."
            : "Se abrió otro escenario. Los resultados mostrados son de la corrida anterior: presiona F5 para recalcular."));
        PushState();
        DetectColumnsAsync();
    }

    private static string ReadShared(string path)
    {
        // FileShare.ReadWrite: Excel may still hold the file open.
        using (var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
        using (var sr = new StreamReader(fs, Encoding.UTF8, true))
            return sr.ReadToEnd();
    }

    private static byte[] ReadSharedBytes(string path)
    {
        using (var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
        using (var ms = new MemoryStream()) { fs.CopyTo(ms); return ms.ToArray(); }
    }

    private static string HashBytes(byte[] bytes)
    {
        using (var sha = System.Security.Cryptography.SHA1.Create()) return Convert.ToBase64String(sha.ComputeHash(bytes));
    }

    private static string EnsureDir(string d) { try { Directory.CreateDirectory(d); } catch { } return d; }

    // ------------------------------------------------------------------ watch the scenario file
    private void WatchScenario()
    {
        if (watcher != null) { watcher.Dispose(); watcher = null; }
        if (string.IsNullOrEmpty(currentScenarioPath) || !File.Exists(currentScenarioPath)) return;
        try
        {
            watcher = new FileSystemWatcher(Path.GetDirectoryName(currentScenarioPath), Path.GetFileName(currentScenarioPath));
            watcher.NotifyFilter = NotifyFilters.LastWrite | NotifyFilters.Size | NotifyFilters.FileName;
            FileSystemEventHandler h = (s, e) => { try { BeginInvoke((Action)(() => { watchTimer.Stop(); watchTimer.Start(); })); } catch { } };
            watcher.Changed += h;
            watcher.Created += h;
            watcher.Renamed += (s, e) => h(s, null);
            watcher.EnableRaisingEvents = true;
        }
        catch { watcher = null; }
    }

    // Debounced (700 ms). Compares content, so our own saves and touch-only writes never notify.
    private void CheckScenarioFile()
    {
        if (string.IsNullOrEmpty(currentScenarioPath) || !File.Exists(currentScenarioPath)) return;
        string h;
        try { h = HashBytes(ReadSharedBytes(currentScenarioPath)); }
        catch { watchTimer.Start(); return; }   // still being written: try again shortly
        if (h == scenarioHash) return;
        scenarioHash = h;
        notice = new Dictionary<string, object>();
        notice["text"] = "«" + Path.GetFileName(currentScenarioPath) + "» se modificó fuera del programa. Los resultados actuales se conservan" +
            (dirty ? "; los cambios sin guardar en el programa se reemplazarán por los del archivo." : ".");
        var m = new Dictionary<string, object>();
        m["type"] = "notice";
        m["notice"] = notice;
        PostSide(m);
        if (!ContainsFocus) FlashWindowNative(Handle, true);
    }

    [System.Runtime.InteropServices.DllImport("user32.dll", EntryPoint = "FlashWindow")]
    private static extern bool FlashWindowNative(IntPtr hwnd, bool invert);

    // ================================================================== bridge
    private void PostSide(Dictionary<string, object> msg)
    {
        if (!sideReady || sideView.CoreWebView2 == null) return;
        sideView.CoreWebView2.PostWebMessageAsString(json.Serialize(msg));
    }

    private void PostDash(Dictionary<string, object> msg)
    {
        if (!dashReady || dashView.CoreWebView2 == null) return;
        dashView.CoreWebView2.PostWebMessageAsString(json.Serialize(msg));
    }

    private static Dictionary<string, object> Msg(string type, string k, object v)
    {
        var m = new Dictionary<string, object>();
        m["type"] = type;
        if (k != null) m[k] = v;
        return m;
    }

    private void PushStatus()
    {
        var m = new Dictionary<string, object>();
        m["type"] = "status";
        m["status"] = statusText;
        m["calcEnabled"] = CalcEnabled;
        m["excelEnabled"] = ExcelEnabled;
        m["busy"] = busy || detecting;
        PostSide(m);
    }

    private void PushState()
    {
        if (!sideReady) return;
        var s = new Dictionary<string, object>();
        s["type"] = "state";
        s["version"] = Version;
        s["baseDir"] = Paths.Base;
        s["dark"] = dark;
        s["input"] = input;
        s["inputMissing"] = !string.IsNullOrEmpty(input) && !File.Exists(input);
        s["output"] = output; s["sheet"] = sheet; s["hojas"] = hojas; s["activeYear"] = activeYear;
        s["mode"] = des.Mode; s["granularity"] = des.Gran; s["target"] = des.Target; s["tolerance"] = des.Tol; s["toleranceUnit"] = des.TolUnit;
        s["dailyTarget"] = des.DailyTarget; s["dailyTolerance"] = des.DailyTol;
        s["mineralMode"] = min.Mode; s["mineralGranularity"] = min.Gran; s["mineralTarget"] = min.Target; s["mineralTolerance"] = min.Tol; s["mineralToleranceUnit"] = min.TolUnit;
        s["mineralDailyTarget"] = min.DailyTarget; s["mineralDailyTolerance"] = min.DailyTol;
        s["chancadoras"] = lastChancadoras; s["candidatos"] = lastCandidatos; s["materiales"] = lastMateriales;
        s["donantes"] = donorsC1.Select(d => d.Id).ToList();
        s["configSheetUsed"] = configSheetUsed;
        s["mineralDisponible"] = mineralDisponible;
        s["mineralChancadoras"] = mineralChancadoras; s["mineralDonantes"] = mineralDonantes; s["mineralMateriales"] = mineralMateriales;
        s["destinoConfig"] = DestinoConfigOut();
        s["desmonteSummary"] = desmonteSummary; s["mineralSummary"] = mineralSummary;
        s["hasResults"] = hasResults;
        s["circuit"] = circuit;
        s["donorsC1"] = PrioToList(donorsC1); s["donorsC2"] = PrioToList(donorsC2);
        s["phasesC1"] = PrioToList(phasesC1); s["phasesC2"] = PrioToList(phasesC2);
        s["donorsMineral"] = PrioToList(donorsMineral); s["phasesMineral"] = PrioToList(phasesMineral);
        s["blocked"] = BlockedOut();
        s["scenario"] = ScenarioName();
        s["dirty"] = dirty;
        s["recent"] = RecentForUi();
        s["notice"] = notice;
        s["detecting"] = detecting;
        s["status"] = statusText;
        s["calcEnabled"] = CalcEnabled;
        s["excelEnabled"] = ExcelEnabled;
        s["busy"] = busy || detecting;
        PostSide(s);
    }

    private async void OnSideMessage(object sender, CoreWebView2WebMessageReceivedEventArgs e)
    {
        Dictionary<string, object> m;
        try { m = json.DeserializeObject(e.TryGetWebMessageAsString()) as Dictionary<string, object>; }
        catch { return; }
        if (m == null) return;
        try
        {
            switch (SVal(m, "type"))
            {
                case "ready":
                    sideReady = true;
                    PushState();
                    // Only the first time: a page reload must not reset the user's lists.
                    if (lastChancadoras.Count == 0 && !detecting) DetectColumnsAsync();
                    break;
                case "set": ApplyField(SVal(m, "field"), SVal(m, "value")); break;
                case "pickInput": PickInput(); break;
                case "pickOutput": PickOutput(); break;
                case "calc": await CalculateAsync(); break;
                case "excel": await OpenExcelAsync(); break;
                case "excelFull": await FullReportAsync(); break;
                case "pptAll": PostDash(Msg("exportPpt", null, null)); break;
                case "openOutputFolder": OpenFolder(Path.GetDirectoryName(Path.GetFullPath(output))); break;
                case "openScenarioFolder": OpenFolder(currentScenarioPath != null ? Path.GetDirectoryName(currentScenarioPath) : EnsureDir(Paths.Escenarios)); break;
                case "openDashboardHtml": if (lastDashboardHtml != null && File.Exists(lastDashboardHtml)) ShellOpen(lastDashboardHtml); break;
                case "scenario": ScenarioOp(SVal(m, "op"), SVal(m, "path")); break;
                case "prio": HandlePrio(m); break;
                case "prioSet": HandlePrioSet(m); break;
                case "prioReset": HandlePrioReset(m); break;
                case "prioCopy": HandlePrioCopy(m); break;
                case "matrix": HandleMatrix(m); break;
                case "destinoConfig": ApplyDestinoConfigMessage(m.ContainsKey("config") ? m["config"] as Dictionary<string, object> : null); break;
                case "circuit": SetCircuit(SVal(m, "circuit"), true); break;
                case "openMaterialEditor": OpenMaterialMatrixForm(SVal(m, "circuit")); break;
                case "theme": ToggleTheme(); break;
                case "close": BeginInvoke((Action)Close); break;
                case "notice": HandleNotice(SVal(m, "op")); break;
                case "dashView": PostDash(Msg("view", "view", SVal(m, "view"))); break;
                case "key": await HandleKey(m); break;
            }
        }
        catch (Exception ex)
        {
            SetStatus("Error: " + ex.Message);
        }
    }

    private void ScenarioOp(string op, string path)
    {
        if (op == "new") NewScenario();
        else if (op == "open") OpenScenario();
        else if (op == "save") SaveScenario(false);
        else if (op == "saveas") SaveScenario(true);
        else if (op == "recent" && path != null) { if (ConfirmDiscard()) OpenScenarioFile(path, false); }
        else if (op == "exit") Close();
    }

    private void HandleNotice(string op)
    {
        notice = null;
        if (op == "reload" && currentScenarioPath != null)
        {
            dirty = false;   // the user explicitly chose the file's version
            OpenScenarioFile(currentScenarioPath, true);
        }
    }

    private void ToggleTheme()
    {
        dark = !dark;
        ApplyTheme();
        SavePrefs();
        PushState();
        PostDash(Msg("theme", "dark", dark));
    }

    private void SetCircuit(string c, bool fromSide)
    {
        circuit = c == "mineral" || c == "Mineral" ? "mineral" : "desmonte";
        if (fromSide) PostDash(Msg("circuit", "circuit", circuit == "mineral" ? "Mineral" : "Desmonte"));
        else PostSide(Msg("circuit", "circuit", circuit));
    }

    private async Task HandleKey(Dictionary<string, object> m)
    {
        string key = (SVal(m, "key") ?? "").ToLowerInvariant();
        bool ctrl = m.ContainsKey("ctrl") && m["ctrl"] is bool && (bool)m["ctrl"];
        bool shift = m.ContainsKey("shift") && m["shift"] is bool && (bool)m["shift"];
        if (key == "f5") { await CalculateAsync(); return; }
        if (!ctrl) return;
        if (key == "e" && !shift) await OpenExcelAsync();
        else if (key == "e" && shift) { if (hasResults) PostDash(Msg("exportPpt", null, null)); }
        else if (key == "n") NewScenario();
        else if (key == "o") OpenScenario();
        else if (key == "s") SaveScenario(shift);
        else if (key == "m" && shift) ToggleTheme();
        else if (key == "c" && shift) PostDash(Msg("view", "view", "comparar"));
    }

    protected override bool ProcessCmdKey(ref Message msg, Keys keyData)
    {
        // Only reached when focus is on the WinForms surface itself (not inside a page).
        if (keyData == Keys.F5) { var t = CalculateAsync(); return true; }
        if (keyData == (Keys.Control | Keys.S)) { SaveScenario(false); return true; }
        return base.ProcessCmdKey(ref msg, keyData);
    }

    private void ApplyField(string field, string value)
    {
        decimal v;
        bool isNum = TryDec(value, out v);
        if (isNum) v = Clamp(v);
        switch (field)
        {
            case "input": input = value; break;
            case "output": output = value; break;
            case "sheet": sheet = value; break;
            case "activeYear": int y; if (int.TryParse(value, out y) && y >= 2000 && y <= 2100) activeYear = y; break;
            case "mode": des.Mode = value == "balanceado" ? "balanceado" : "objetivo_fijo"; break;
            case "granularity": des.Gran = value == "diario" ? "diario" : "semanal"; break;
            case "toleranceUnit": des.TolUnit = value == "%" ? "%" : "Mt"; break;
            case "target": if (isNum) des.Target = v; break;
            case "tolerance": if (isNum) des.Tol = v; break;
            case "dailyTarget": if (isNum) des.DailyTarget = v; break;
            case "dailyTolerance": if (isNum) des.DailyTol = v; break;
            case "mineralMode": min.Mode = value == "balanceado" ? "balanceado" : "objetivo_fijo"; break;
            case "mineralGranularity": min.Gran = value == "diario" ? "diario" : "semanal"; break;
            case "mineralToleranceUnit": min.TolUnit = value == "%" ? "%" : "Mt"; break;
            case "mineralTarget": if (isNum) min.Target = v; break;
            case "mineralTolerance": if (isNum) min.Tol = v; break;
            case "mineralDailyTarget": if (isNum) min.DailyTarget = v; break;
            case "mineralDailyTolerance": if (isNum) min.DailyTol = v; break;
            default: return;
        }
        MarkChanged();
        PushState();
        if (field == "input" || field == "sheet") DetectColumnsAsync();
    }

    private List<PrioItem> PrioListByName(string name)
    {
        switch (name)
        {
            case "donorsC1": return donorsC1;
            case "donorsC2": return donorsC2;
            case "phasesC1": return phasesC1;
            case "phasesC2": return phasesC2;
            case "donorsMineral": return donorsMineral;
            case "phasesMineral": return phasesMineral;
        }
        return null;
    }

    private void HandlePrio(Dictionary<string, object> m)
    {
        var list = PrioListByName(SVal(m, "list"));
        if (list == null) return;
        int idx = list.FindIndex(x => x.Id == SVal(m, "id"));
        if (idx < 0) return;
        list[idx].Active = m.ContainsKey("active") && m["active"] is bool && (bool)m["active"];
        MarkChanged();
        PushState();
    }

    // Full new order from the drag & drop columns. Only reorders: ids must be the same set.
    private void HandlePrioSet(Dictionary<string, object> m)
    {
        var list = PrioListByName(SVal(m, "list"));
        var items = ReadPrio(m, "items");
        if (list == null || items == null) return;
        if (items.Count != list.Count || !new HashSet<string>(items.Select(i => i.Id)).SetEquals(list.Select(i => i.Id))) { PushState(); return; }
        list.Clear();
        list.AddRange(items);
        MarkChanged();
        PushState();
    }

    private void HandlePrioReset(Dictionary<string, object> m)
    {
        foreach (var name in ToStringList(m.ContainsKey("lists") ? m["lists"] : null))
        {
            var list = PrioListByName(name);
            if (list == null) continue;
            List<string> src = name.StartsWith("phases") ? detPhases : name == "donorsMineral" ? detMineralDonors : detDonors;
            list.Clear();
            foreach (var id in src) list.Add(new PrioItem(id));
        }
        MarkChanged();
        PushState();
        SetStatus("Prioridad restablecida al orden detectado en el Excel.");
    }

    private void HandlePrioCopy(Dictionary<string, object> m)
    {
        foreach (var name in ToStringList(m.ContainsKey("from") ? m["from"] : null))
        {
            var src = PrioListByName(name);
            if (src == null || name.Length < 3) continue;
            string other = name.EndsWith("C1") ? name.Substring(0, name.Length - 2) + "C2" : name.Substring(0, name.Length - 2) + "C1";
            var dst = PrioListByName(other);
            if (dst == null) continue;
            dst.Clear();
            dst.AddRange(src.Select(x => x.Clone()));
        }
        MarkChanged();
        PushState();
        SetStatus("Orden copiado a la otra chancadora.");
    }

    // internal: also called by MaterialMatrixForm (the native matrix window).
    internal void HandleMatrix(Dictionary<string, object> m)
    {
        string op = SVal(m, "op");
        if (op == "cell")
        {
            string dest = SVal(m, "dest"), mat = SVal(m, "mat");
            bool ok = m.ContainsKey("allowed") && m["allowed"] is bool && (bool)m["allowed"];
            HashSet<string> set;
            if (!materialBlocked.TryGetValue(dest, out set)) { set = new HashSet<string>(); materialBlocked[dest] = set; }
            if (ok) set.Remove(mat); else set.Add(mat);
            MarkChanged();
            return;
        }
        List<string> dests = m.ContainsKey("dests") ? ToStringList(m["dests"]) : null;
        if (op == "all")
        {
            if (dests == null) materialBlocked = new Dictionary<string, HashSet<string>>();
            else foreach (var d in dests) materialBlocked.Remove(d);
        }
        else if (op == "reset")
        {
            if (dests == null) materialBlocked = CloneBlocked(defaultBlocked);
            else foreach (var d in dests)
            {
                materialBlocked.Remove(d);
                if (defaultBlocked.ContainsKey(d)) materialBlocked[d] = new HashSet<string>(defaultBlocked[d]);
            }
        }
        else if (op == "none")
        {
            List<string> mats = m.ContainsKey("mats") ? ToStringList(m["mats"]) : new List<string>();
            if (dests != null) foreach (var d in dests) materialBlocked[d] = new HashSet<string>(mats);
        }
        MarkChanged();
        PushState();
    }

    internal Dictionary<string, HashSet<string>> GetMaterialBlocked() { return materialBlocked; }

    private static Dictionary<string, HashSet<string>> CloneBlocked(Dictionary<string, HashSet<string>> src)
    {
        var copy = new Dictionary<string, HashSet<string>>();
        foreach (var kv in src) copy[kv.Key] = new HashSet<string>(kv.Value);
        return copy;
    }

    private void OpenMaterialMatrixForm(string c)
    {
        bool isDesmonte = c != "mineral";
        var chs = isDesmonte ? lastChancadoras : mineralChancadoras;
        var dons = isDesmonte ? donorsC1.Select(d => d.Id).ToList() : mineralDonantes;
        var mats = isDesmonte ? lastMateriales : mineralMateriales;
        using (var f = new MaterialMatrixForm(this, isDesmonte ? "Desmonte" : "Mineral", chs, dons, mats, dark))
            f.ShowDialog(this);
        PushState();
        RefocusPage();
    }

    private void ApplyDestinoConfigMessage(Dictionary<string, object> configObj)
    {
        if (configObj == null) return;
        var newConfig = ParseDestinoConfigDict(configObj);
        if (newConfig == null || !newConfig.Values.Any(r => r["destino"] == "Receptor"))
        {
            MessageBox.Show(this, "Debes marcar al menos un destino como Receptor.", "Columnas detectadas");
            PushState();
            return;
        }
        destinoConfig = newConfig;
        MarkChanged();
        SetStatus("Configuración de destinos actualizada. Detectando circuitos…");
        DetectColumnsAsync();
    }

    // ================================================================== dashboard bridge
    private async void OnDashMessage(object sender, CoreWebView2WebMessageReceivedEventArgs e)
    {
        Dictionary<string, object> m;
        try { m = json.DeserializeObject(e.TryGetWebMessageAsString()) as Dictionary<string, object>; }
        catch { return; }
        if (m == null) return;
        try
        {
            switch (SVal(m, "type"))
            {
                case "dashReady":
                    dashReady = true;
                    var init = new Dictionary<string, object>();
                    init["type"] = "init"; init["version"] = Version; init["dark"] = dark; init["recent"] = RecentForUi();
                    PostDash(init);
                    PushRunList();
                    if (sessionRuns.Count > 0) PostRun(sessionRuns[sessionRuns.Count - 1], "results");
                    break;
                case "circuit": SetCircuit(SVal(m, "circuit"), false); break;
                case "needRun": SendRun(SVal(m, "id")); break;
                case "openResultFile": OpenResultFile(); break;
                case "openRecent": if (ConfirmDiscard()) OpenScenarioFile(SVal(m, "path"), false); break;
                case "copy": CopyRich(SVal(m, "text"), SVal(m, "html")); break;
                case "copyImage": CopyPng(DataUrlBytes(SVal(m, "png"))); break;
                case "saveImage": SavePng(DataUrlBytes(SVal(m, "png")), SVal(m, "name")); break;
                case "captureRect": await CaptureRectAsync(m); break;
                case "pptChart": await PptChartAsync(m); break;
                case "close": BeginInvoke((Action)Close); break;
                case "key": await HandleKey(m); break;
            }
        }
        catch (Exception ex)
        {
            SetStatus("Error: " + ex.Message);
        }
    }

    private void PushRunList()
    {
        ScanResultFiles();
        var list = new List<object>();
        var sessionPaths = new HashSet<string>(sessionRuns.Select(r => r.Path), StringComparer.OrdinalIgnoreCase);
        foreach (var r in sessionRuns)
            list.Add(new Dictionary<string, object> { { "id", r.Id }, { "escenario", r.Escenario }, { "fecha", r.Fecha }, { "origen", "sesion" } });
        foreach (var kv in fileRuns)
        {
            if (sessionPaths.Contains(kv.Key)) continue;
            var meta = ReadResultMeta(kv.Key);
            if (meta == null) continue;
            list.Add(new Dictionary<string, object> { { "id", "f|" + kv.Key }, { "escenario", meta[0] }, { "fecha", meta[1] }, { "origen", "archivo" } });
        }
        var msg = new Dictionary<string, object>();
        msg["type"] = "runList";
        msg["list"] = list;
        PostDash(msg);
    }

    private void ScanResultFiles()
    {
        var dirs = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        dirs.Add(Paths.Outputs);
        try { if (!string.IsNullOrEmpty(output)) dirs.Add(Path.GetDirectoryName(Path.GetFullPath(output))); } catch { }
        foreach (var d in dirs)
        {
            try
            {
                if (!Directory.Exists(d)) continue;
                foreach (var f in Directory.GetFiles(d, "* - Resultados.json")) fileRuns[f] = f;
            }
            catch { }
        }
    }

    // The first 4 KB are enough: the file starts with the metadata, then "circuitos".
    private static string[] ReadResultMeta(string path)
    {
        try
        {
            string head;
            using (var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
            {
                var buf = new byte[4096];
                int n = fs.Read(buf, 0, buf.Length);
                head = Encoding.UTF8.GetString(buf, 0, n);
            }
            if (!head.Contains("Material Shift - Resultados")) return null;
            var me = Regex.Match(head, "\"escenario\":\"((?:[^\"\\\\]|\\\\.)*)\"");
            var mf = Regex.Match(head, "\"fecha\":\"([^\"]*)\"");
            return new[] { me.Success ? Regex.Unescape(me.Groups[1].Value) : Path.GetFileName(path), mf.Success ? mf.Groups[1].Value : "" };
        }
        catch { return null; }
    }

    private void PostRun(SessionRun r, string type)
    {
        if (!dashReady) return;
        string head = "{\"type\":\"" + type + "\",\"id\":" + json.Serialize(r.Id) + ",\"origen\":\"" + (r.Id.StartsWith("f|") ? "archivo" : "sesion") + "\",\"run\":";
        dashView.CoreWebView2.PostWebMessageAsString(head + r.Json + "}");
    }

    private void SendRun(string id)
    {
        if (string.IsNullOrEmpty(id)) return;
        var r = sessionRuns.FirstOrDefault(x => x.Id == id);
        if (r == null && id.StartsWith("f|"))
        {
            string path = id.Substring(2);
            if (!File.Exists(path)) { PostDash(Msg("toast", "text", "No se encontró " + path)); return; }
            r = new SessionRun { Id = id, Path = path, Json = File.ReadAllText(path, Encoding.UTF8) };
        }
        if (r != null) PostRun(r, "run");
    }

    private void OpenResultFile()
    {
        using (var dlg = new OpenFileDialog())
        {
            dlg.Filter = "Resultados de Material Shift (*Resultados.json)|*Resultados.json|JSON (*.json)|*.json";
            dlg.InitialDirectory = EnsureDir(Paths.Outputs);
            if (ShowCentered(dlg) != DialogResult.OK) return;
            if (ReadResultMeta(dlg.FileName) == null) { MessageBox.Show(this, "El archivo no es un resultado de Material Shift.", AppTitle); return; }
            fileRuns[dlg.FileName] = dlg.FileName;
            PushRunList();
            SendRun("f|" + dlg.FileName);
        }
    }

    // ================================================================== clipboard & export
    private static byte[] DataUrlBytes(string dataUrl)
    {
        if (string.IsNullOrEmpty(dataUrl)) return null;
        int i = dataUrl.IndexOf(',');
        return Convert.FromBase64String(i >= 0 ? dataUrl.Substring(i + 1) : dataUrl);
    }

    private static byte[] CfHtml(string fragment)
    {
        const string tpl = "Version:0.9\r\nStartHTML:{0:D10}\r\nEndHTML:{1:D10}\r\nStartFragment:{2:D10}\r\nEndFragment:{3:D10}\r\n";
        const string pre = "<html><head><meta charset=\"utf-8\"></head><body><!--StartFragment-->";
        const string post = "<!--EndFragment--></body></html>";
        var enc = new UTF8Encoding(false);
        int startHtml = enc.GetByteCount(string.Format(tpl, 0, 0, 0, 0));
        int startFrag = startHtml + enc.GetByteCount(pre);
        int endFrag = startFrag + enc.GetByteCount(fragment);
        int endHtml = endFrag + enc.GetByteCount(post);
        return enc.GetBytes(string.Format(tpl, startHtml, endHtml, startFrag, endFrag) + pre + fragment + post);
    }

    private void CopyRich(string text, string html)
    {
        var data = new DataObject();
        data.SetData(DataFormats.UnicodeText, text ?? "");
        data.SetData(DataFormats.Text, text ?? "");
        if (!string.IsNullOrEmpty(html)) data.SetData(DataFormats.Html, new MemoryStream(CfHtml(html)));
        Clipboard.SetDataObject(data, true, 5, 100);
        SetStatus(string.IsNullOrEmpty(html) ? "Copiado al portapapeles (texto)." : "Copiado al portapapeles con formato.");
    }

    private void CopyPng(byte[] png)
    {
        if (png == null) return;
        using (var ms = new MemoryStream(png))
        using (var img = Image.FromStream(ms))
        {
            var data = new DataObject();
            data.SetData(DataFormats.Bitmap, true, new Bitmap(img));
            data.SetData("PNG", false, new MemoryStream(png));
            Clipboard.SetDataObject(data, true, 5, 100);
        }
        SetStatus("Imagen copiada al portapapeles.");
    }

    private void SavePng(byte[] png, string name)
    {
        if (png == null) return;
        using (var dlg = new SaveFileDialog())
        {
            dlg.Filter = "Imagen PNG (*.png)|*.png";
            dlg.FileName = SafeFile(name ?? "Grafico") + ".png";
            dlg.InitialDirectory = EnsureDir(Path.GetDirectoryName(Path.GetFullPath(output)));
            if (ShowCentered(dlg) != DialogResult.OK) return;
            File.WriteAllBytes(dlg.FileName, png);
            SetStatus("Imagen guardada: " + dlg.FileName);
        }
    }

    private static string SafeFile(string s)
    {
        foreach (char c in Path.GetInvalidFileNameChars()) s = s.Replace(c, '_');
        s = s.Trim();
        return s.Length > 90 ? s.Substring(0, 90) : s;
    }

    private async Task CaptureRectAsync(Dictionary<string, object> m)
    {
        var r = m["rect"] as Dictionary<string, object>;
        if (r == null) return;
        double dpr = Convert.ToDouble(r["dpr"]);
        using (var ms = new MemoryStream())
        {
            await dashView.CoreWebView2.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png, ms);
            ms.Position = 0;
            using (var full = new Bitmap(ms))
            {
                var rect = Rectangle.Intersect(new Rectangle(0, 0, full.Width, full.Height), new Rectangle(
                    (int)(Convert.ToDouble(r["x"]) * dpr), (int)(Convert.ToDouble(r["y"]) * dpr),
                    (int)(Convert.ToDouble(r["w"]) * dpr), (int)(Convert.ToDouble(r["h"]) * dpr)));
                if (rect.Width < 2 || rect.Height < 2) return;
                using (var crop = full.Clone(rect, PixelFormat.Format32bppArgb))
                using (var outMs = new MemoryStream())
                {
                    crop.Save(outMs, ImageFormat.Png);
                    CopyPng(outMs.ToArray());
                }
            }
        }
        SetStatus("Tabla copiada como imagen (parte visible).");
    }

    private async Task PptChartAsync(Dictionary<string, object> m)
    {
        if (busy) return;
        bool save = m.ContainsKey("save") && m["save"] is bool && (bool)m["save"];
        string name = SafeFile(SVal(m, "name") ?? "Grafico");
        string pptx;
        if (save)
        {
            using (var dlg = new SaveFileDialog())
            {
                dlg.Filter = "PowerPoint (*.pptx)|*.pptx";
                dlg.FileName = name + ".pptx";
                dlg.InitialDirectory = EnsureDir(Path.GetDirectoryName(Path.GetFullPath(output)));
                if (ShowCentered(dlg) != DialogResult.OK) return;
                pptx = dlg.FileName;
            }
        }
        else pptx = Path.Combine(Path.GetTempPath(), "materialshift_" + Guid.NewGuid().ToString("N") + ".pptx");
        string spec = Path.Combine(Path.GetTempPath(), "materialshift_" + Guid.NewGuid().ToString("N") + ".json");
        File.WriteAllText(spec, json.Serialize(m["spec"]), new UTF8Encoding(false));
        SetBusy(true, save ? "Creando PowerPoint…" : "Preparando gráfico de PowerPoint…");
        try
        {
            var res = await worker.RunAsync(new List<string> { "--pptx-chart", spec, "--output", pptx });
            if (res.ExitCode != 0 || !File.Exists(pptx)) { SetBusy(false, "No se pudo crear el PowerPoint."); ShowEngineError("No se pudo crear el PowerPoint", res.Output); return; }
            if (save)
            {
                SetBusy(false, "PowerPoint guardado: " + pptx);
                ShellOpen(pptx);
                return;
            }
            string err = await Task.Run(() => CopyPptShape(pptx));
            if (err == null) SetBusy(false, "Gráfico copiado: pégalo en PowerPoint (Ctrl+V) como gráfico editable.");
            else SetBusy(false, "No se pudo copiar con PowerPoint (" + err + "). Usa «Exportar a PowerPoint (.pptx)…».");
        }
        finally
        {
            if (busy) SetBusy(false, statusText);
            try { File.Delete(spec); } catch { }
        }
    }

    // Opens the one-slide pptx with PowerPoint (no window) and copies its chart shape,
    // so the clipboard holds a native, editable PowerPoint chart (same as SimA).
    private static string CopyPptShape(string path)
    {
        string err = null;
        var t = new Thread(() =>
        {
            try
            {
                Type tp = Type.GetTypeFromProgID("PowerPoint.Application");
                if (tp == null) { err = "PowerPoint no está instalado"; return; }
                dynamic app = Activator.CreateInstance(tp);
                int before = app.Presentations.Count;
                dynamic pres = app.Presentations.Open(path, -1, 0, 0);
                pres.Slides.Item(1).Shapes.Item(1).Copy();
                pres.Close();
                if (before == 0 && app.Presentations.Count == 0) app.Quit();
            }
            catch (Exception ex) { err = ex.Message; }
        });
        t.SetApartmentState(ApartmentState.STA);
        t.Start();
        t.Join();
        try { File.Delete(path); } catch { }
        return err;
    }

    private static void ShellOpen(string path)
    {
        try { Process.Start(new ProcessStartInfo { FileName = path, UseShellExecute = true }); } catch { }
    }

    private static void OpenFolder(string dir)
    {
        if (string.IsNullOrEmpty(dir)) return;
        EnsureDir(dir);
        ShellOpen(dir);
    }

    // ================================================================== inputs
    private void PickInput()
    {
        using (var dialog = new OpenFileDialog())
        {
            dialog.Filter = "Excel (*.xlsx)|*.xlsx";
            dialog.InitialDirectory = File.Exists(input) ? Path.GetDirectoryName(input) : EnsureDir(Paths.Inputs);
            if (ShowCentered(dialog) == DialogResult.OK)
            {
                input = dialog.FileName;
                MarkChanged();
                PushState();
                DetectColumnsAsync();
            }
        }
    }

    private void PickOutput()
    {
        using (var dialog = new SaveFileDialog())
        {
            dialog.Filter = "Excel (*.xlsx)|*.xlsx";
            dialog.DefaultExt = "xlsx";
            dialog.FileName = Path.GetFileName(output);
            try { dialog.InitialDirectory = EnsureDir(Path.GetDirectoryName(Path.GetFullPath(output))); } catch { }
            if (ShowCentered(dialog) == DialogResult.OK)
            {
                output = dialog.FileName;
                MarkChanged();
                PushState();
            }
        }
    }

    // Reads chancadoras/donantes/fases/materials from the Excel (detect_destinations() in
    // the engine) and rebuilds the priority lists in the sheet's natural order. With the
    // engine's parse cache this takes ~0.2 s after the first read of a file.
    private async void DetectColumnsAsync()
    {
        if (string.IsNullOrWhiteSpace(input) || !File.Exists(input)) { ApplyPendingScenario(); PushState(); return; }
        if (detecting) { redetect = true; return; }
        detecting = true;
        PushState();
        try
        {
            do
            {
                redetect = false;
                SetStatus("Leyendo el Excel y detectando chancadoras, donantes, fases y materiales…");
                var argv = new List<string> { "--nogui", "--list-columns", "--input", input, "--sheet", sheet, "--cache-dir", Paths.Cache };
                if (destinoConfig.Count > 0) { argv.Add("--destino-config"); argv.Add(json.Serialize(DestinoConfigOut())); }
                var sw = Stopwatch.StartNew();
                var result = await worker.RunAsync(argv);
                if (!redetect) ApplyDetection(result, sw.Elapsed.TotalSeconds);
            } while (redetect);
        }
        finally
        {
            detecting = false;
            PushState();
        }
    }

    private void ApplyDetection(ProcResult result, double secs)
    {
        const string marker = "COLUMNS_RESULT:";
        int idx = result.Output.IndexOf(marker, StringComparison.Ordinal);
        if (idx < 0)
        {
            SetStatus("No se pudieron detectar las columnas del Excel.");
            ShowEngineError("Error al detectar columnas", result.Output);
            ApplyPendingScenario();
            return;
        }
        Dictionary<string, object> data;
        try { data = json.Deserialize<Dictionary<string, object>>(result.Output.Substring(idx + marker.Length).Trim()); }
        catch { SetStatus("Respuesta inválida al detectar columnas."); ApplyPendingScenario(); return; }

        hojas = ToStringList(data.ContainsKey("hojas") ? data["hojas"] : null);
        if (data.ContainsKey("error"))
        {
            ApplyPendingScenario();
            SetStatus(Convert.ToString(data["error"]) + " Elige la hoja en Inputs.");
            return;
        }
        List<string> donantes = ToStringList(data.ContainsKey("donantes") ? data["donantes"] : null);
        lastChancadoras = ToStringList(data.ContainsKey("chancadoras") ? data["chancadoras"] : null);
        lastCandidatos = ToStringList(data.ContainsKey("candidatos") ? data["candidatos"] : null);
        lastMateriales = ToStringList(data.ContainsKey("materiales") ? data["materiales"] : null);
        configSheetUsed = data.ContainsKey("config_sheet_used") && Convert.ToBoolean(data["config_sheet_used"]);
        mineralDisponible = data.ContainsKey("mineral_disponible") && Convert.ToBoolean(data["mineral_disponible"]);
        mineralChancadoras = ToStringList(data.ContainsKey("mineral_chancadoras") ? data["mineral_chancadoras"] : null);
        mineralDonantes = ToStringList(data.ContainsKey("mineral_donantes") ? data["mineral_donantes"] : null);
        mineralMateriales = ToStringList(data.ContainsKey("mineral_materiales") ? data["mineral_materiales"] : null);
        if (!mineralDisponible && circuit == "mineral") SetCircuit("desmonte", true);

        // Keep destinoConfig only when it is file-specific (a real Config sheet or the in-app
        // edit); auto-detected defaults must never be resent for another file (v19 fix).
        destinoConfig = new Dictionary<string, Dictionary<string, string>>();
        if (configSheetUsed && data.ContainsKey("circuitos"))
            destinoConfig = ParseDestinoConfigDict(data["circuitos"] as Dictionary<string, object>) ?? destinoConfig;

        defaultBlocked = new Dictionary<string, HashSet<string>>();
        foreach (var key in new[] { "bloqueos_default", "bloqueos_default_mineral" })
        {
            var bd = data.ContainsKey(key) ? data[key] as Dictionary<string, object> : null;
            if (bd != null) foreach (var kv in bd) defaultBlocked[kv.Key] = new HashSet<string>(ToStringList(kv.Value));
        }
        materialBlocked = CloneBlocked(defaultBlocked);

        if (data.ContainsKey("anio_sugerido") && data["anio_sugerido"] != null)
        {
            int y;
            if (int.TryParse(Convert.ToString(data["anio_sugerido"]), out y) && y >= 2000 && y <= 2100) activeYear = y;
        }
        List<string> fases = ToStringList(data.ContainsKey("fases") ? data["fases"] : null);
        detDonors = donantes; detPhases = fases; detMineralDonors = mineralDonantes;
        donorsC1.Clear(); donorsC2.Clear();
        foreach (var n in donantes) { donorsC1.Add(new PrioItem(n)); donorsC2.Add(new PrioItem(n)); }
        if (fases.Count > 0)
        {
            phasesC1.Clear(); phasesC2.Clear();
            foreach (var f in fases) { phasesC1.Add(new PrioItem(f)); phasesC2.Add(new PrioItem(f)); }
        }
        donorsMineral.Clear();
        foreach (var n in mineralDonantes) donorsMineral.Add(new PrioItem(n));
        phasesMineral.Clear();
        foreach (var f in fases) phasesMineral.Add(new PrioItem(f));

        bool hadPending = pendingScenario != null;
        string msg = donantes.Count == 0
            ? "El Excel no tiene columnas de donantes reconocibles."
            : "Detectado: " + donantes.Count + " donantes, " + fases.Count + " fases, " + lastMateriales.Count + " materiales" +
              (mineralDisponible ? " · Mineral: " + mineralChancadoras.Count + " receptor(es), " + mineralDonantes.Count + " donante(s)" : "") +
              "  (" + secs.ToString("0.0") + " s)";
        ApplyPendingScenario();
        if (!hadPending) { PushState(); SetStatus(msg); }
    }

    // ================================================================== calculation
    private string PriorityJson(List<PrioItem> c1, List<PrioItem> c2)
    {
        // Keyed by the ACTUAL chancadora names, never the literal "Chw2a_1"/"Chw2a_2" (v19).
        var d = new Dictionary<string, object>();
        string n1 = lastChancadoras.Count > 0 ? lastChancadoras[0] : "Chw2a_1";
        string n2 = lastChancadoras.Count > 1 ? lastChancadoras[1] : "Chw2a_2";
        d[n1] = c1.Where(i => i.Active).Select(i => i.Id).ToList();
        if (lastChancadoras.Count != 1) d[n2] = c2.Where(i => i.Active).Select(i => i.Id).ToList();
        return json.Serialize(d);
    }

    private string MaterialMatrixJson()
    {
        if (lastMateriales.Count == 0) return null;
        // Desmonte AND Mineral destinos (v19 only sent Desmonte's, so edits to the Mineral
        // matrix never reached the engine).
        var valid = new HashSet<string>(lastChancadoras.Concat(donorsC1.Select(d => d.Id)).Concat(mineralChancadoras).Concat(mineralDonantes));
        var dict = new Dictionary<string, object>();
        foreach (var kv in materialBlocked)
            if (valid.Contains(kv.Key) && kv.Value.Count > 0) dict[kv.Key] = kv.Value.OrderBy(x => x).Cast<object>().ToList();
        return json.Serialize(dict);
    }

    private static string Inv(double v) { return v.ToString("R", System.Globalization.CultureInfo.InvariantCulture); }
    private static string Inv(decimal v) { return v.ToString(System.Globalization.CultureInfo.InvariantCulture); }

    private List<string> BuildArgs(string outPath, string modeFlag)
    {
        var a = new List<string> {
            "--nogui", modeFlag, "--input", input, "--output", outPath, "--sheet", sheet,
            "--target-mode", des.Mode, "--target-mt", Inv(des.Target), "--tolerance-mt", Inv(des.TolMt()),
            "--donor-priority", PriorityJson(donorsC1, donorsC2), "--phase-priority", PriorityJson(phasesC1, phasesC2),
            "--granularity", des.Gran, "--daily-tolerance-mt", Inv(des.DailyTol), "--daily-target-mt", Inv(des.DailyTarget),
            "--donantes-override", json.Serialize(donorsC1.Select(d => d.Id).ToList()),
            "--active-year", activeYear.ToString(), "--cache-dir", Paths.Cache, "--scenario-name", ScenarioName() };
        string mm = MaterialMatrixJson();
        if (mm != null) { a.Add("--material-matrix"); a.Add(mm); }
        if (destinoConfig.Count > 0) { a.Add("--destino-config"); a.Add(json.Serialize(DestinoConfigOut())); }
        if (mineralChancadoras.Count > 0)
        {
            a.AddRange(new[] {
                "--mineral-donor-priority", json.Serialize(donorsMineral.Where(d => d.Active).Select(d => d.Id).ToList()),
                "--mineral-phase-priority", json.Serialize(phasesMineral.Where(d => d.Active).Select(d => d.Id).ToList()),
                "--mineral-target-mt", Inv(min.Target), "--mineral-tolerance-mt", Inv(min.TolMt()),
                "--mineral-target-mode", min.Mode, "--mineral-granularity", min.Gran,
                "--mineral-daily-target-mt", Inv(min.DailyTarget), "--mineral-daily-tolerance-mt", Inv(min.DailyTol) });
        }
        return a;
    }

    private bool ValidateInputs()
    {
        if (string.IsNullOrWhiteSpace(input) || !File.Exists(input))
        {
            MessageBox.Show(this, "Falta el Archivo base (Inputs › Archivo base *).", AppTitle, MessageBoxButtons.OK, MessageBoxIcon.Information);
            return false;
        }
        if (hojas.Count > 0 && !hojas.Contains(sheet))
        {
            MessageBox.Show(this, "La hoja «" + sheet + "» no existe en el archivo. Elige la hoja en Inputs.", AppTitle, MessageBoxButtons.OK, MessageBoxIcon.Information);
            return false;
        }
        if (string.IsNullOrWhiteSpace(output)) output = DefaultOutput();
        return true;
    }

    private async Task CalculateAsync()
    {
        if (busy || detecting) return;
        if (!ValidateInputs()) return;
        SetBusy(true, "Calculando Desmonte" + (mineralChancadoras.Count > 0 ? " y Mineral" : "") + "…");
        var sw = Stopwatch.StartNew();
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(output)));
            var res = await worker.RunAsync(BuildArgs(output, "--dashboard-only"));
            const string marker = "MODEL_RESULT:";
            int idx = res.Output.IndexOf(marker, StringComparison.Ordinal);
            if (res.ExitCode != 0 || idx < 0) { SetBusy(false, "Error al calcular."); ShowEngineError("Error al calcular", res.Output); return; }
            var data = json.Deserialize<Dictionary<string, object>>(res.Output.Substring(idx + marker.Length).Trim());
            desmonteSummary = data.ContainsKey("Desmonte") ? data["Desmonte"] as Dictionary<string, object> : null;
            mineralSummary = data.ContainsKey("Mineral") ? data["Mineral"] as Dictionary<string, object> : null;
            lastResultsJson = SVal(data, "results_json");
            lastDashboardHtml = SVal(data, "dashboard_html");
            hasResults = true;
            excelFresh = false;
            if (lastResultsJson != null && File.Exists(lastResultsJson))
            {
                var run = new SessionRun
                {
                    Id = "s" + (++runCounter) + "|" + lastResultsJson,
                    Escenario = ScenarioName(),
                    Fecha = DateTime.Now.ToString("dd/MM/yyyy HH:mm:ss"),
                    Path = lastResultsJson,
                    Json = File.ReadAllText(lastResultsJson, Encoding.UTF8)
                };
                sessionRuns.Add(run);
                if (sessionRuns.Count > 12) sessionRuns.RemoveAt(0);   // keep the last 12 runs of the session in memory
                PushRunList();
                PostRun(run, "results");
            }
            string msg = "Listo en " + sw.Elapsed.TotalSeconds.ToString("0.0") + " s · Desmonte: " + SVal(desmonteSummary, "movimientos") + " movimientos";
            if (mineralSummary != null) msg += " · Mineral: " + SVal(mineralSummary, "movimientos") + " movimientos";
            busy = false;
            PushState();
            SetStatus(msg + ". Ctrl+E para el Excel.");
        }
        catch (Exception ex)
        {
            SetBusy(false, "Error al calcular: " + ex.Message);
        }
    }

    private async Task OpenExcelAsync()
    {
        if (busy) return;
        if (!hasResults) { MessageBox.Show(this, "Primero calcula (F5).", AppTitle); return; }
        if (!excelFresh || !File.Exists(output))
        {
            SetBusy(true, "Generando el Excel del Plan Modificado…");
            var sw = Stopwatch.StartNew();
            var res = await worker.RunAsync(BuildArgs(output, "--excel-only"));
            if (res.ExitCode != 0)
            {
                SetBusy(false, "Error al generar el Excel.");
                ShowEngineError("Error al generar el Excel", res.Output);
                return;
            }
            excelFresh = true;
            SetBusy(false, "Excel generado en " + sw.Elapsed.TotalSeconds.ToString("0.0") + " s: " + output);
        }
        ShellOpen(output);
    }

    private async Task FullReportAsync()
    {
        if (busy || !hasResults) return;
        string path = Path.Combine(Path.GetDirectoryName(Path.GetFullPath(output)), Path.GetFileNameWithoutExtension(output) + " - Reporte completo.xlsx");
        SetBusy(true, "Generando el reporte Excel completo (ambos circuitos, con validaciones)…");
        var sw = Stopwatch.StartNew();
        var res = await worker.RunAsync(BuildArgs(path, "--full-report"));
        if (res.ExitCode != 0) { SetBusy(false, "Error al generar el reporte."); ShowEngineError("Error al generar el reporte", res.Output); return; }
        SetBusy(false, "Reporte generado en " + sw.Elapsed.TotalSeconds.ToString("0.0") + " s: " + path);
        ShellOpen(path);
    }

    private void ShowEngineError(string title, string text)
    {
        text = text ?? "";
        if (text.Contains("PermissionError") || text.Contains("Permission denied"))
            text = "El archivo de salida está abierto en otro programa (probablemente Excel). Ciérralo e intenta de nuevo.\n\n" + Tail(text, 4);
        else text = Tail(text, 25);
        MessageBox.Show(this, text, title, MessageBoxButtons.OK, MessageBoxIcon.Error);
        RefocusPage();
    }

    private static string Tail(string s, int lines)
    {
        var parts = s.Replace("\r\n", "\n").TrimEnd().Split('\n');
        return string.Join("\n", parts.Skip(Math.Max(0, parts.Length - lines)));
    }

    // ================================================================== helpers
    private static List<string> ToStringList(object value)
    {
        var list = new List<string>();
        var items = value as System.Collections.IEnumerable;
        if (items == null || value is string) return list;
        foreach (var item in items) if (item != null) list.Add(item.ToString());
        return list;
    }

    public static string QuoteArg(string a)
    {
        if (a == null) return "\"\"";
        if (a.Length > 0 && a.IndexOfAny(new[] { ' ', '\t', '"' }) < 0) return a;
        var sb = new StringBuilder("\"");
        int bs = 0;
        foreach (char c in a)
        {
            if (c == '\\') { bs++; continue; }
            if (c == '"') { sb.Append('\\', bs * 2 + 1).Append('"'); bs = 0; continue; }
            sb.Append('\\', bs).Append(c);
            bs = 0;
        }
        sb.Append('\\', bs * 2).Append('"');
        return sb.ToString();
    }

    public static ProcResult RunProcess(string file, string args)
    {
        var psi = new ProcessStartInfo
        {
            FileName = file,
            Arguments = args,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
            CreateNoWindow = true,
            WorkingDirectory = Paths.App
        };
        psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
        psi.EnvironmentVariables["PYTHONUTF8"] = "1";
        using (var p = Process.Start(psi))
        {
            var err = p.StandardError.ReadToEndAsync();
            string outp = p.StandardOutput.ReadToEnd();
            p.WaitForExit();
            return new ProcResult { ExitCode = p.ExitCode, Output = outp + Environment.NewLine + err.Result };
        }
    }
}

// Native window for the Destino x Material matrix (independent, resizable, centered).
// All state lives in the owner; every change goes through HandleMatrix().
public class MaterialMatrixForm : Form
{
    private readonly MaterialShiftForm owner;
    private readonly List<string> chancadoras, donantes, materiales;
    private readonly DataGridView grid = new DataGridView();
    private bool suppressEvents = false;

    public MaterialMatrixForm(MaterialShiftForm owner, string label, List<string> chancadoras, List<string> donantes, List<string> materiales, bool dark)
    {
        this.owner = owner;
        this.chancadoras = chancadoras;
        this.donantes = donantes;
        this.materiales = materiales;
        Text = "Materiales · " + label;
        StartPosition = FormStartPosition.CenterParent;
        Width = Math.Min(1100, 280 + materiales.Count * 76);
        Height = 620;
        MinimumSize = new Size(560, 360);
        Font = new Font("Segoe UI", 9F);
        ShowInTaskbar = false;
        try { Icon = owner.Icon; } catch { }

        var root = new TableLayoutPanel { Dock = DockStyle.Fill, RowCount = 3, ColumnCount = 1, Padding = new Padding(14) };
        root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        var hint = new Label
        {
            Text = "Marca los materiales que cada destino puede recibir y entregar. Sin marcar: ese material no se toca en ese destino. Clic en el encabezado de una columna para marcarla o desmarcarla completa.",
            AutoSize = false, Height = 38, Dock = DockStyle.Top, ForeColor = Color.FromArgb(111, 109, 104)
        };
        root.Controls.Add(hint, 0, 0);
        BuildGrid();
        root.Controls.Add(grid, 0, 1);
        Height = Math.Min(660, Math.Max(380, 210 + grid.Rows.Count * 26));   // fit the rows, no empty grey area

        var acts = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.RightToLeft, AutoSize = true };
        var closeBtn = new Button { Text = "Cerrar", Height = 32, Width = 90 };
        closeBtn.Click += (s, e) => Close();
        CancelButton = closeBtn;
        var resetBtn = new Button { Text = "Restablecer", Height = 32, Width = 100 };
        resetBtn.Click += (s, e) => { owner.HandleMatrix(new Dictionary<string, object> { { "op", "reset" }, { "dests", AllDests() } }); RefreshGridValues(); };
        var noneBtn = new Button { Text = "Marcar ninguna", Height = 32, Width = 110 };
        noneBtn.Click += (s, e) => { owner.HandleMatrix(new Dictionary<string, object> { { "op", "none" }, { "dests", AllDests() }, { "mats", materiales } }); RefreshGridValues(); };
        var allBtn = new Button { Text = "Marcar todo", Height = 32, Width = 95 };
        allBtn.Click += (s, e) => { owner.HandleMatrix(new Dictionary<string, object> { { "op", "all" }, { "dests", AllDests() } }); RefreshGridValues(); };
        acts.Controls.Add(closeBtn);
        acts.Controls.Add(resetBtn);
        acts.Controls.Add(noneBtn);
        acts.Controls.Add(allBtn);
        root.Controls.Add(acts, 0, 2);
        Controls.Add(root);
        if (dark)
        {
            BackColor = Color.FromArgb(22, 33, 46); ForeColor = Color.FromArgb(230, 237, 245); hint.ForeColor = Color.FromArgb(147, 163, 184);
            grid.BackgroundColor = BackColor; grid.DefaultCellStyle.BackColor = Color.FromArgb(27, 40, 54); grid.DefaultCellStyle.ForeColor = ForeColor;
            grid.EnableHeadersVisualStyles = false; grid.ColumnHeadersDefaultCellStyle.BackColor = Color.FromArgb(34, 49, 66); grid.ColumnHeadersDefaultCellStyle.ForeColor = ForeColor;
            foreach (Control c in acts.Controls) { c.BackColor = Color.FromArgb(27, 40, 54); c.ForeColor = ForeColor; ((Button)c).FlatStyle = FlatStyle.Flat; }
        }
    }

    private List<string> AllDests() { return chancadoras.Concat(donantes).ToList(); }

    private void BuildGrid()
    {
        grid.Dock = DockStyle.Fill;
        grid.AllowUserToAddRows = false;
        grid.AllowUserToDeleteRows = false;
        grid.AllowUserToResizeRows = false;
        grid.RowHeadersVisible = false;
        grid.SelectionMode = DataGridViewSelectionMode.CellSelect;
        grid.AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.None;
        grid.EditMode = DataGridViewEditMode.EditOnEnter;
        grid.BackgroundColor = Color.White;
        grid.BorderStyle = BorderStyle.FixedSingle;
        grid.GridColor = Color.FromArgb(232, 236, 241);
        grid.CellBorderStyle = DataGridViewCellBorderStyle.SingleHorizontal;
        grid.RowTemplate.Height = 26;
        grid.ColumnHeadersHeight = 30;
        grid.ColumnHeadersHeightSizeMode = DataGridViewColumnHeadersHeightSizeMode.DisableResizing;
        grid.EnableHeadersVisualStyles = false;
        grid.ColumnHeadersDefaultCellStyle.BackColor = Color.FromArgb(241, 244, 248);
        grid.ColumnHeadersDefaultCellStyle.Font = new Font("Segoe UI", 9F, FontStyle.Bold);
        grid.ColumnHeadersDefaultCellStyle.SelectionBackColor = grid.ColumnHeadersDefaultCellStyle.BackColor;
        grid.DefaultCellStyle.SelectionBackColor = Color.FromArgb(226, 236, 248);
        grid.DefaultCellStyle.SelectionForeColor = Color.FromArgb(20, 32, 51);
        Shown += (s, e) => grid.ClearSelection();
        grid.Columns.Add(new DataGridViewTextBoxColumn { Name = "destino", HeaderText = "Destino", Width = 170, ReadOnly = true, Frozen = true });
        foreach (var mat in materiales)
            grid.Columns.Add(new DataGridViewCheckBoxColumn { Name = mat, HeaderText = mat, Width = 68, SortMode = DataGridViewColumnSortMode.NotSortable });
        AddGroup("RECEPTORES", chancadoras);
        AddGroup("DONANTES", donantes);
        grid.CurrentCellDirtyStateChanged += (s, e) => { if (grid.IsCurrentCellDirty) grid.CommitEdit(DataGridViewDataErrorContexts.Commit); };
        grid.CellValueChanged += Grid_CellValueChanged;
        grid.ColumnHeaderMouseClick += (s, e) =>
        {
            if (e.ColumnIndex <= 0) return;
            string mat = grid.Columns[e.ColumnIndex].Name;
            var blocked = owner.GetMaterialBlocked();
            bool anyBlocked = AllDests().Any(d => blocked.ContainsKey(d) && blocked[d].Contains(mat));
            foreach (var d in AllDests())
                owner.HandleMatrix(new Dictionary<string, object> { { "op", "cell" }, { "dest", d }, { "mat", mat }, { "allowed", anyBlocked } });
            RefreshGridValues();
        };
    }

    private void AddGroup(string title, List<string> dests)
    {
        if (dests.Count == 0) return;
        var hRow = grid.Rows[grid.Rows.Add()];
        hRow.DefaultCellStyle.BackColor = Color.FromArgb(240, 242, 245);
        hRow.DefaultCellStyle.ForeColor = Color.FromArgb(90, 98, 110);
        hRow.DefaultCellStyle.Font = new Font(Font, FontStyle.Bold);
        hRow.Cells[0].Value = title;
        for (int c = 1; c < grid.Columns.Count; c++) hRow.Cells[c] = new DataGridViewTextBoxCell { Value = "" };
        hRow.ReadOnly = true;
        var blocked = owner.GetMaterialBlocked();
        foreach (var d in dests)
        {
            var row = grid.Rows[grid.Rows.Add()];
            row.Tag = d;
            row.Cells[0].Value = d;
            HashSet<string> b;
            blocked.TryGetValue(d, out b);
            for (int c = 1; c < grid.Columns.Count; c++) row.Cells[c].Value = b == null || !b.Contains(grid.Columns[c].Name);
        }
    }

    private void Grid_CellValueChanged(object sender, DataGridViewCellEventArgs e)
    {
        if (suppressEvents || e.RowIndex < 0 || e.ColumnIndex <= 0) return;
        var row = grid.Rows[e.RowIndex];
        string dest = row.Tag as string;
        if (dest == null) return;
        bool allowed = Convert.ToBoolean(row.Cells[e.ColumnIndex].Value ?? false);
        owner.HandleMatrix(new Dictionary<string, object> { { "op", "cell" }, { "dest", dest }, { "mat", grid.Columns[e.ColumnIndex].Name }, { "allowed", allowed } });
    }

    private void RefreshGridValues()
    {
        suppressEvents = true;
        var blocked = owner.GetMaterialBlocked();
        foreach (DataGridViewRow row in grid.Rows)
        {
            string dest = row.Tag as string;
            if (dest == null) continue;
            HashSet<string> b;
            blocked.TryGetValue(dest, out b);
            for (int c = 1; c < grid.Columns.Count; c++) row.Cells[c].Value = b == null || !b.Contains(grid.Columns[c].Name);
        }
        suppressEvents = false;
    }
}
