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
            // Ignore SSL certificate errors for testing
            ServicePointManager.ServerCertificateValidationCallback += (s, cert, chain, sslPolicyErrors) => true;
        }

        // Fetch Counterparty List
        private async void btnFetchFromAPI_Click(object sender, RibbonControlEventArgs e)
        {
            try
            {
                ddlCounterparty.Items.Clear();

                string apiUrl = "https://your-api-endpoint.com/api/counterparties"; // ✅ Replace with actual API
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
                    RibbonDropDownItem item = Globals.Factory.GetRibbonFactory().CreateRibbonDropDownItem();
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

        // Show popup with selected counterparty details
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

        // Submit Counterparty
        private async void btnSubmit_Click(object sender, RibbonControlEventArgs e)
        {
            try
            {
                var selectedId = ddlCounterparty.SelectedItem?.Label;
                if (string.IsNullOrEmpty(selectedId))
                {
                    MessageBox.Show("Please select a Counterparty.");
                    return;
                }

                string apiUrl = "https://your-api-endpoint.com/api/counterparty/details"; // ✅ Replace with API2 URL
                var requestData = new { CID = selectedId };
                var content = new StringContent(JsonConvert.SerializeObject(requestData), Encoding.UTF8, "application/json");

                var response = await client.PostAsync(apiUrl, content);

                if (!response.IsSuccessStatusCode)
                {
                    MessageBox.Show($"Error Submitting Counterparty: {response.StatusCode}");
                    return;
                }

                string json = await response.Content.ReadAsStringAsync();
                var result = JsonConvert.DeserializeObject<CounterpartyDetails>(json);

                // Populate dropdowns with API2 response
                ddlCurrency.Items.Clear();
                ddlPeriod.Items.Clear();
                ddlBasis.Items.Clear();
                ddlType.Items.Clear();

                ddlCurrency.Items.Add(CreateItem(result.Currency));
                foreach (var p in result.Period) ddlPeriod.Items.Add(CreateItem(p));
                foreach (var b in result.Basis) ddlBasis.Items.Add(CreateItem(b));
                foreach (var t in result.Type) ddlType.Items.Add(CreateItem(t));

                ddlPeriod.SelectedItem = ddlPeriod.Items[0];
                ddlBasis.SelectedItem = ddlBasis.Items[1]; // Default text2 if present
                ddlType.SelectedItem = ddlType.Items[0];

                txtFromYear.Text = result.FromYear.ToString();
                txtToYear.Text = result.ToYear.ToString();

                MessageBox.Show("Counterparty details loaded successfully!");
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Error Submitting Counterparty: {ex.Message}");
            }
        }

        // Fetch Final Data
        private async void btnFetchFinalData_Click(object sender, RibbonControlEventArgs e)
        {
            try
            {
                var selectedId = ddlCounterparty.SelectedItem?.Label;
                if (string.IsNullOrEmpty(selectedId))
                {
                    MessageBox.Show("Please select a Counterparty.");
                    return;
                }

                string apiUrl = "https://your-api-endpoint.com/api/finaldata"; // ✅ Replace with API3 URL

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

        private RibbonDropDownItem CreateItem(string label)
        {
            var item = Globals.Factory.GetRibbonFactory().CreateRibbonDropDownItem();
            item.Label = label;
            return item;
        }

        // Write JSON data to Excel Sheet
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
