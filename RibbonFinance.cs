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
        // ==============================
        // Fields
        // ==============================
        private readonly HttpClient client = new HttpClient();
        private List<string> counterparties = new List<string>();

        // ==============================
        // Constructor
        // ==============================
        public RibbonFinance()
            : base(Globals.Factory.GetRibbonFactory())
        {
            InitializeComponent();
        }

        // ==============================
        // Ribbon Load Event
        // ==============================
        private void RibbonFinance_Load(object sender, RibbonUIEventArgs e)
        {
            // Optional: Initialize default dropdowns or states
        }

        // ==============================
        // Button: Fetch Counterparties
        // ==============================
        private async void btnFetchCounterparties_Click(object sender, RibbonControlEventArgs e)
        {
            try
            {
                string apiUrl = "https://mocki.io/v1/fee0df8b-fc19-4b5b-b5d3-3b2218b2212d"; // Mock API
                string jsonResponse = await client.GetStringAsync(apiUrl);

                var responseObj = JsonConvert.DeserializeObject<Api1Response>(jsonResponse);
                counterparties = responseObj?.Counterparties ?? new List<string>();

                drpCounterparties.Items.Clear();
                foreach (var name in counterparties)
                {
                    drpCounterparties.Items.Add(CreateItem(name));
                }

                MessageBox.Show($"Fetched {counterparties.Count} counterparties successfully!", "Success");
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Error fetching counterparties:\n{ex.Message}", "Error");
            }
        }

        // ==============================
        // Button: Submit Counterparty
        // ==============================
        private async void btnSubmitCounterparty_Click(object sender, RibbonControlEventArgs e)
        {
            try
            {
                if (drpCounterparties.SelectedItem == null)
                {
                    MessageBox.Show("Please select a counterparty first.");
                    return;
                }

                string selectedCounterparty = drpCounterparties.SelectedItem.Label;
                string apiUrl = $"https://mocki.io/v1/4bdf2b94-54b8-4cb9-8b3c-ec5ddf5551b3?name={selectedCounterparty}";
                string jsonResponse = await client.GetStringAsync(apiUrl);

                var details = JsonConvert.DeserializeObject<CounterpartyDetails>(jsonResponse);
                if (details == null)
                {
                    MessageBox.Show("No details found for the selected counterparty.");
                    return;
                }

                PopulateDropdown(drpCurrency, details.Currency);
                PopulateDropdown(drpPeriod, details.Period);
                PopulateDropdown(drpBasis, details.Basis);
                PopulateDropdown(drpType, details.Type);

                numFromYear.Text = details.FromYear.ToString();
                numToYear.Text = details.ToYear.ToString();

                MessageBox.Show("Counterparty details loaded successfully!");
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Error fetching counterparty details:\n{ex.Message}", "Error");
            }
        }

        // ==============================
        // Button: Show Balance Sheet
        // ==============================
        private async void btnShowBalanceSheet_Click(object sender, RibbonControlEventArgs e)
        {
            try
            {
                if (drpCounterparties.SelectedItem == null)
                {
                    MessageBox.Show("Please select a counterparty first.");
                    return;
                }

                string selectedCounterparty = drpCounterparties.SelectedItem.Label;
                string apiUrl = $"https://mocki.io/v1/0abde292-3180-4a1a-98e4-0f35d1dc642e?counterparty={selectedCounterparty}";
                string jsonResponse = await client.GetStringAsync(apiUrl);

                var balanceData = JsonConvert.DeserializeObject<List<BalanceSheetItem>>(jsonResponse);
                if (balanceData == null || balanceData.Count == 0)
                {
                    MessageBox.Show("No balance sheet data found.");
                    return;
                }

                var sheet = Globals.ThisAddIn.Application.ActiveSheet;
                sheet.Cells[1, 1].Value = "Counterparty";
                sheet.Cells[1, 2].Value = "Year";
                sheet.Cells[1, 3].Value = "Revenue";
                sheet.Cells[1, 4].Value = "Profit";

                int row = 2;
                foreach (var item in balanceData)
                {
                    sheet.Cells[row, 1].Value = selectedCounterparty;
                    sheet.Cells[row, 2].Value = item.Year;
                    sheet.Cells[row, 3].Value = item.Revenue;
                    sheet.Cells[row, 4].Value = item.Profit;
                    row++;
                }

                MessageBox.Show("Balance sheet data inserted successfully!");
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Error displaying balance sheet:\n{ex.Message}", "Error");
            }
        }

        // ==============================
        // Helper Methods
        // ==============================
        private void PopulateDropdown(RibbonDropDown dropdown, string singleValue)
        {
            dropdown.Items.Clear();
            if (!string.IsNullOrEmpty(singleValue))
                dropdown.Items.Add(CreateItem(singleValue));
        }

        private void PopulateDropdown(RibbonDropDown dropdown, List<string> values)
        {
            dropdown.Items.Clear();
            if (values == null || values.Count == 0) return;

            foreach (var val in values)
                dropdown.Items.Add(CreateItem(val));
        }

        private RibbonDropDownItem CreateItem(string label)
        {
            var item = Globals.Factory.GetRibbonFactory().CreateRibbonDropDownItem();
            item.Label = label;
            return item;
        }
    }

    // ==============================
    // Data Models
    // ==============================
    public class Api1Response
    {
        public List<string> Counterparties { get; set; }
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
