using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Office.Tools.Ribbon;
using Excel = Microsoft.Office.Interop.Excel;
using Newtonsoft.Json;

namespace ExcelFinanceAddIn
{
    public partial class RibbonFinance
    {
        private static readonly HttpClient client = new HttpClient();
        private List<Counterparty> counterparties = new List<Counterparty>();

        private void RibbonFinance_Load(object sender, RibbonUIEventArgs e)
        {
            // Ignore SSL certificate validation for testing
            ServicePointManager.ServerCertificateValidationCallback += (s, cert, chain, sslPolicyErrors) => true;
        }

        // 1️⃣ Fetch Counterparty List (API1)
        private async void btnFetchAPI_Click(object sender, RibbonControlEventArgs e)
        {
            try
            {
                ddlCounterparty.Items.Clear();

                string apiUrl = "https://your-api-endpoint.com/api/counterparties"; // Replace with your actual API1
                var response = await client.GetAsync(apiUrl);

                if (!response.IsSuccessStatusCode)
                {
                    MessageBox.Show($"Error Fetching Counterparties: {response.StatusCode}");
                    return;
                }

                string json = await response.Content.ReadAsStringAsync();
                counterparties = JsonConvert.DeserializeObject<List<Counterparty>>(json);

                foreach (var cp in counterparties)
                {
                    var item = Globals.Factory.GetRibbonFactory().CreateRibbonDropDownItem();
                    item.Label = cp.CID.ToString();
                    ddlCounterparty.Items.Add(item);
                }

                MessageBox.Show("Counterparties loaded successfully!");
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Error Fetching Counterparties: {ex.Message}");
            }
        }

        // 2️⃣ Show selected Counterparty details (Popup)
        private void ddlCounterparty_SelectionChanged(object sender, RibbonControlEventArgs e)
        {
            var selectedId = ddlCounterparty.SelectedItem?.Label;
            if (string.IsNullOrEmpty(selectedId)) return;

            var cp = counterparties.Find(c => c.CID.ToString() == selectedId);
            if (cp != null)
            {
                string message = $"CID | CName | ShortName\n{cp.CID} | {cp.CName} | {cp.ShortName}";
                MessageBox.Show(message, "Counterparty Details");
            }
        }

        // 3️⃣ Submit Counterparty (API2)
        private async void btnSubmitCounterparty_Click(object sender, RibbonControlEventArgs e)
        {
            try
            {
                var selectedId = ddlCounterparty.SelectedItem?.Label;
                if (string.IsNullOrEmpty(selectedId))
                {
                    MessageBox.Show("Please select a Counterparty.");
                    return;
                }

                string apiUrl = "https://your-api-endpoint.com/api/counterparty/details"; // Replace with API2
                var requestData = new { CID = selectedId };
                var content = new StringContent(JsonConvert.SerializeObject(requestData), Encoding.UTF8, "application/json");

                var response = await client.PostAsync(apiUrl, content);
                if (!response.IsSuccessStatusCode)
                {
                    MessageBox.Show($"Error Submitting Counterparty: {response.StatusCode}");
                    return;
                }

                string json = await response.Content.ReadAsStringAsync();
                var details = JsonConvert.DeserializeObject<CounterpartyDetails>(json);

                // Populate dropdowns with response
                ddlCurrency.Items.Clear();
                ddlPeriod.Items.Clear();
                ddlBasis.Items.Clear();
                ddlType.Items.Clear();

                ddlCurrency.Items.Add(CreateItem(details.Currency));
                foreach (var p in details.Period) ddlPeriod.Items.Add(CreateItem(p));
                foreach (var b in details.Basis) ddlBasis.Items.Add(CreateItem(b));
                foreach (var t in details.Type) ddlType.Items.Add(CreateItem(t));

                ddlCurrency.SelectedItem = ddlCurrency.Items[0];
                ddlPeriod.SelectedItem = ddlPeriod.Items[0];
                ddlBasis.SelectedItem = ddlBasis.Items.Count > 1 ? ddlBasis.Items[1] : ddlBasis.Items[0];
                ddlType.SelectedItem = ddlType.Items[0];

                txtFromYear.Text = details.FromYear.ToString();
                txtToYear.Text = details.ToYear.ToString();

                MessageBox.Show("Counterparty details loaded successfully!");
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Error Submitting Counterparty: {ex.Message}");
            }
        }

        // 4️⃣ Fetch Final Data (API3)
        private async void btnFetchFinalData_Click(object sender, RibbonControlEventArgs e)
        {
            try
            {
                var selectedId = ddlCounterparty.SelectedItem?.Label;
                if (string.IsNullOrEmpty(selectedId))
                {
                    MessageBox.Show("Please select a Counterparty first.");
                    return;
                }

                string apiUrl = "https://your-api-endpoint.com/api/finaldata"; // Replace with API3
                var requestData = new
                {
                    CID = selectedId,
                    FromYear = txtFromYear.Text,
                    ToYear = txtToYear.Text,
                    Period = ddlPeriod.SelectedItem?.Label,
                    Basis = ddlBasis.SelectedItem?.Label,
                    Type = ddlType.SelectedItem?.Label
                };

                var content = new StringContent(JsonConvert.SerializeObject(requestData), Encoding.UTF8, "application/json");
                var response = await client.PostAsync(apiUrl, content);

                if (!response.IsSuccessStatusCode)
                {
                    MessageBox.Show($"Error Fetching Final Data: {response.StatusCode}");
                    return;
                }

                string json = await response.Content.ReadAsStringAsync();
                var data = JsonConvert.DeserializeObject<List<Dictionary<string, object>>>(json);

                WriteJsonToExcel(data);
                MessageBox.Show("Data populated successfully in Excel!");
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Error Fetching Final Data: {ex.Message}");
            }
        }

        // 🔧 Helper to create dropdown item
        private RibbonDropDownItem CreateItem(string label)
        {
            var item = Globals.Factory.GetRibbonFactory().CreateRibbonDropDownItem();
            item.Label = label;
            return item;
        }

        // 📊 Write JSON Data to Excel Sheet
        private void WriteJsonToExcel(List<Dictionary<string, object>> jsonData)
        {
            if (jsonData == null || jsonData.Count == 0)
            {
                MessageBox.Show("No data to write to Excel.");
                return;
            }

            Excel.Worksheet sheet = Globals.ThisAddIn.Application.ActiveSheet;
            var headers = new List<string>(jsonData[0].Keys);

            // Write headers
            for (int i = 0; i < headers.Count; i++)
                sheet.Cells[1, i + 1].Value = headers[i];

            // Write rows
            for (int i = 0; i < jsonData.Count; i++)
                for (int j = 0; j < headers.Count; j++)
                    sheet.Cells[i + 2, j + 1].Value = jsonData[i][headers[j]];
        }
    }

    // Data Models
    public class Counterparty
    {
        public int CID { get; set; }
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
}
