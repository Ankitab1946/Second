using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Office.Tools.Ribbon;
using Newtonsoft.Json;

namespace ExcelFinanceAddIn
{
    public partial class RibbonFinance : RibbonBase
    {
        // ----------------------------
        // Fields
        // ----------------------------
        private readonly HttpClient client = new HttpClient();
        private List<Counterparty> counterparties = new List<Counterparty>();

        // ----------------------------
        // Constructor
        // ----------------------------
        public RibbonFinance()
            : base(Globals.Factory.GetRibbonFactory())
        {
            InitializeComponent();
        }

        // ----------------------------
        // Ribbon Load Event
        // ----------------------------
        private void RibbonFinance_Load(object sender, RibbonUIEventArgs e)
        {
            // Optionally initialize dropdowns with defaults
        }

        // ----------------------------
        // Button: Fetch Counterparties (API1)
        // ----------------------------
        private async void btnFetchAPI_Click(object sender, RibbonControlEventArgs e)
        {
            try
            {
                string apiUrl = "https://mocki.io/v1/fee0df8b-fc19-4b5b-b5d3-3b2218b2212d"; // Mock API returning JSON array
                string jsonResponse = await client.GetStringAsync(apiUrl);

                counterparties = JsonConvert.DeserializeObject<List<Counterparty>>(jsonResponse);

                ddlCounterparty.Items.Clear();
                foreach (var cp in counterparties)
                {
                    ddlCounterparty.Items.Add(CreateItem(cp.CID)); // Show only CID
                }

                MessageBox.Show($"Fetched {counterparties.Count} counterparties successfully!");
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Error fetching counterparties:\n{ex.Message}");
            }
        }

        // ----------------------------
        // Dropdown selection tooltip
        // ----------------------------
        private void ddlCounterparty_SelectionChanged(object sender, RibbonControlEventArgs e)
        {
            if (ddlCounterparty.SelectedItem == null) return;

            string selectedCID = ddlCounterparty.SelectedItem.Label;
            var cp = counterparties.Find(c => c.CID == selectedCID);

            if (cp != null)
            {
                MessageBox.Show($"CID | CName | ShortName\n{cp.CID} | {cp.CName} | {cp.ShortName}", "Counterparty Details");
            }
        }

        // ----------------------------
        // Button: Submit Counterparty (API2)
        // ----------------------------
        private async void btnSubmitCounterparty_Click(object sender, RibbonControlEventArgs e)
        {
            try
            {
                if (ddlCounterparty.SelectedItem == null)
                {
                    MessageBox.Show("Please select a counterparty first.");
                    return;
                }

                string selectedCID = ddlCounterparty.SelectedItem.Label;
                string apiUrl = $"https://mocki.io/v1/4bdf2b94-54b8-4cb9-8b3c-ec5ddf5551b3?cid={selectedCID}";
                string jsonResponse = await client.GetStringAsync(apiUrl);

                var details = JsonConvert.DeserializeObject<CounterpartyDetails>(jsonResponse);
                if (details == null)
                {
                    MessageBox.Show("No details returned from API2.");
                    return;
                }

                PopulateDropdown(ddlCurrency, new List<string> { details.Currency });
                PopulateDropdown(ddlPeriod, details.Period);
                PopulateDropdown(ddlBasis, details.Basis);
                PopulateDropdown(ddlType, details.Type);

                txtFromYear.Text = details.FromYear.ToString();
                txtToYear.Text = details.ToYear.ToString();

                MessageBox.Show("Counterparty details loaded!");
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Error submitting counterparty:\n{ex.Message}");
            }
        }

        // ----------------------------
        // Button: Fetch Final Data (API3)
        // ----------------------------
        private async void btnFetchFinalData_Click(object sender, RibbonControlEventArgs e)
        {
            try
            {
                if (ddlCounterparty.SelectedItem == null)
                {
                    MessageBox.Show("Please select a counterparty first.");
                    return;
                }

                string cid = ddlCounterparty.SelectedItem.Label;
                string currency = ddlCurrency.SelectedItem?.Label ?? "USD";
                string period = ddlPeriod.SelectedItem?.Label ?? "Annual";
                string basis = ddlBasis.SelectedItem?.Label ?? "text2";
                string type = ddlType.SelectedItem?.Label ?? "Cons";

                int fromYear = int.TryParse(txtFromYear.Text, out var fy) ? fy : 2007;
                int toYear = int.TryParse(txtToYear.Text, out var ty) ? ty : 2008;

                string apiUrl = "https://mocki.io/v1/0abde292-3180-4a1a-98e4-0f35d1dc642e"; // API3 returning final data
                var requestData = new
                {
                    CID = cid,
                    FromYear = fromYear,
                    ToYear = toYear,
                    Period = period,
                    Basis = basis,
                    Type = type
                };

                var content = new StringContent(JsonConvert.SerializeObject(requestData), System.Text.Encoding.UTF8, "application/json");
                var response = await client.PostAsync(apiUrl, content);
                response.EnsureSuccessStatusCode();

                var jsonResponse = await response.Content.ReadAsStringAsync();
                var finalData = JsonConvert.DeserializeObject<List<BalanceSheetItem>>(jsonResponse);

                // Insert into Excel
                var sheet = Globals.ThisAddIn.Application.ActiveSheet;
                sheet.Cells[1, 1].Value = "CID";
                sheet.Cells[1, 2].Value = "Year";
                sheet.Cells[1, 3].Value = "Revenue";
                sheet.Cells[1, 4].Value = "Profit";

                int row = 2;
                foreach (var item in finalData)
                {
                    sheet.Cells[row, 1].Value = cid;
                    sheet.Cells[row, 2].Value = item.Year;
                    sheet.Cells[row, 3].Value = item.Revenue;
                    sheet.Cells[row, 4].Value = item.Profit;
                    row++;
                }

                MessageBox.Show("Final data fetched and inserted into Excel!");
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Error fetching final data:\n{ex.Message}");
            }
        }

        // ----------------------------
        // Helpers
        // ----------------------------
        private void PopulateDropdown(RibbonDropDown ddl, List<string> values)
        {
            ddl.Items.Clear();
            if (values == null) return;
            foreach (var val in values)
                ddl.Items.Add(CreateItem(val));
        }

        private RibbonDropDownItem CreateItem(string label)
        {
            var item = Globals.Factory.GetRibbonFactory().CreateRibbonDropDownItem();
            item.Label = label;
            return item;
        }
    }

    // ==============================
    // Models
    // ==============================
    public class Counterparty
    {
        public string CID { get; set; }
        public string CName { get; set; }
        public string ShortName { get; set; }
    }

    public class CounterpartyDetails
    {
        public string Currency { get; set; }
        public List<string> Period { get; set; }
        public List<string> Basis { get; set; }
        public List<string> Type { get; set; }
        public int FromYear { get; set; }
        public int ToYear { get; set; }
    }

    public class BalanceSheetItem
    {
        public int Year { get; set; }
        public double Revenue { get; set; }
        public double Profit { get; set; }
    }
}


//Extra code added for dynamically added data into excel

// --- Parse API3 JSON dynamically ---
var responseText = await response.Content.ReadAsStringAsync();
MessageBox.Show("Response:\n" + responseText);

// Parse as JObject
var json = JObject.Parse(responseText);
var highlights = json["Financialhighlights"] as JArray;

if (highlights == null || highlights.Count == 0)
{
    MessageBox.Show("No financial highlights found in response.");
    return;
}

// Create Excel sheet
Excel.Worksheet sheet = Globals.ThisAddIn.Application.ActiveSheet;
sheet.Cells.Clear(); // clear previous content
int row = 1;

// Extract all column names dynamically from the first record
var allKeys = ((JObject)highlights[0])
                .Properties()
                .Select(p => p.Name)
                // Exclude unwanted keys
                .Where(k => k != "HS_1" && k != "ID2")
                .ToList();

// Write headers
int col = 1;
foreach (var key in allKeys)
{
    sheet.Cells[row, col].Value = key;
    col++;
}

// Write data rows
row = 2;
foreach (var record in highlights)
{
    col = 1;
    foreach (var key in allKeys)
    {
        sheet.Cells[row, col].Value = record[key]?.ToString();
        col++;
    }
    row++;
}

// Autofit columns for better readability
sheet.Columns.AutoFit();
MessageBox.Show($"✅ Written {highlights.Count} records with {allKeys.Count} columns (excluded: HS_1, ID2).");
